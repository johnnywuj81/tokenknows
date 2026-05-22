"""generation_service · 同步 workflow + helpers 单测.

不测 5 阶段 async pipeline (需要 LLM mock), 只覆盖:
- _placeholder_content / _pick_diverse_events / _initial_progress
- get_asset / list_chapters / list_chapter_evidence / get_progress / list_assets
- update_chapter_content
- approve_chapter / reject_chapter / submit_asset_for_review (T09)
- publish_asset / get_publish_record / list_publish_records_for_asset (T11)
- delete_asset / clone_asset
- _find_chapter / _refresh_asset_approval / _refresh_redaction_state
- redaction confirm/exempt (T10)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.schemas.asset import Asset, Chapter
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_asset(asset_id: str = "a1", project_id: str = "p1", status: str = "draft") -> Asset:
    return Asset(
        id=asset_id,
        project_id=project_id,
        type="weekly_report",
        title="test",
        status=status,  # type: ignore[arg-type]
        current_version=1,
        template_id="t",
        created_by="anon",
        created_at=_now(),
        updated_at=_now(),
    )


def _make_chapter(idx: int = 0, asset_id: str = "a1") -> Chapter:
    return Chapter(
        id=f"ch-{asset_id}-{idx}",
        asset_id=asset_id,
        order_index=idx,
        title=f"§{idx}",
        content=f"content {idx}",
    )


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    """每个 test 隔离全局 dict + 跳过 SQLite 写."""
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_e = dict(gen._evidence_by_chapter)
    snap_p = dict(gen._progress)
    snap_pr = dict(gen._publish_records)
    snap_r = dict(gen._redaction_jobs)
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._publish_records.clear()
    gen._redaction_jobs.clear()
    # 跳过 SQLite 持久化 (避免污染真 DB)
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._publish_records.clear()
    gen._redaction_jobs.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._evidence_by_chapter.update(snap_e)
    gen._progress.update(snap_p)
    gen._publish_records.update(snap_pr)
    gen._redaction_jobs.update(snap_r)


def _register(asset: Asset, chapters: list[Chapter]) -> None:
    gen._assets[asset.id] = asset
    gen._chapters[asset.id] = chapters


# ─── 简单查询 + 占位 ───────────────────────────────────────────────


def test_placeholder_content_contains_title() -> None:
    out = gen._placeholder_content("§1 概述", "weekly_report")
    assert "§1 概述" in out
    assert "weekly_report" in out


def test_get_asset_returns_none_for_missing() -> None:
    assert gen.get_asset("a-fake") is None


def test_get_asset_returns_after_register() -> None:
    a = _make_asset("a1")
    _register(a, [])
    assert gen.get_asset("a1") is a


def test_list_chapters_empty_for_missing_asset() -> None:
    assert gen.list_chapters("a-fake") == []


def test_list_chapters_returns_registered() -> None:
    a = _make_asset("a1")
    chs = [_make_chapter(0), _make_chapter(1)]
    _register(a, chs)
    assert gen.list_chapters("a1") == chs


def test_list_chapter_evidence_empty() -> None:
    assert gen.list_chapter_evidence("a1", "ch-fake") == []


def test_get_progress_missing() -> None:
    assert gen.get_progress("a-fake") is None


def test_list_assets_by_project() -> None:
    _register(_make_asset("a1", project_id="p-A"), [])
    _register(_make_asset("a2", project_id="p-A"), [])
    _register(_make_asset("a3", project_id="p-B"), [])
    assert len(gen.list_assets("p-A")) == 2
    assert len(gen.list_assets("p-B")) == 1
    assert gen.list_assets("p-nonexistent") == []


def test_list_assets_sorted_by_created_at_desc() -> None:
    """Regression 2026-05-22: 新 generate 的 asset 应排在列表最前 (created_at desc).

    Bug 复现: 之前用 _assets.values() 返回 dict 插入顺序, 老 asset 排在前,
    用户看不到刚点 '开始生成' 创建的新文档, 误以为按钮没工作.
    """
    from datetime import datetime, timedelta, timezone
    base = datetime.now(timezone.utc)
    # 故意按非时间顺序 register (middle → old → new)
    a_mid = _make_asset("a-mid", project_id="p-X")
    a_old = _make_asset("a-old", project_id="p-X")
    a_new = _make_asset("a-new", project_id="p-X")
    # 显式设置 created_at 制造时间倒置
    object.__setattr__(a_mid, "created_at", base - timedelta(hours=1))
    object.__setattr__(a_old, "created_at", base - timedelta(hours=24))
    object.__setattr__(a_new, "created_at", base)
    _register(a_mid, [])
    _register(a_old, [])
    _register(a_new, [])
    result = gen.list_assets("p-X")
    # 最新的必须在 index 0
    assert [a.id for a in result] == ["a-new", "a-mid", "a-old"]


# ─── _find_chapter ─────────────────────────────────────────────────


def test_find_chapter_returns_none_for_unknown() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    assert gen._find_chapter("a1", "ch-fake") is None


def test_find_chapter_returns_matching() -> None:
    chs = [_make_chapter(0), _make_chapter(1)]
    _register(_make_asset("a1"), chs)
    assert gen._find_chapter("a1", chs[1].id) is chs[1]


# ─── update_chapter_content (T06 Phase 2) ──────────────────────────


def test_update_chapter_content_persists() -> None:
    ch = _make_chapter(0)
    _register(_make_asset("a1"), [ch])
    result = gen.update_chapter_content("a1", ch.id, "new content here")
    assert result is ch
    assert ch.content == "new content here"


def test_update_chapter_content_missing_asset_returns_none() -> None:
    assert gen.update_chapter_content("a-fake", "ch", "x") is None


def test_update_chapter_content_missing_chapter_returns_none() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    assert gen.update_chapter_content("a1", "ch-fake", "x") is None


# ─── T09 审批 ──────────────────────────────────────────────────────


def test_approve_chapter_sets_approved() -> None:
    ch = _make_chapter(0)
    _register(_make_asset("a1"), [ch])
    result = gen.approve_chapter("a1", ch.id)
    assert result is ch
    assert ch.approval_state == "approved"


def test_approve_chapter_missing_returns_none() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    assert gen.approve_chapter("a1", "ch-fake") is None


def test_approve_all_chapters_lifts_asset_approval() -> None:
    """所有 chapter approved → asset.approval_state=approved + status=approved."""
    chs = [_make_chapter(0), _make_chapter(1)]
    a = _make_asset("a1", status="in_review")
    _register(a, chs)
    gen.approve_chapter("a1", chs[0].id)
    assert a.approval_state == "pending"   # 还有 1 个 pending
    gen.approve_chapter("a1", chs[1].id)
    # 全部 approved
    assert a.approval_state == "approved"


def test_reject_chapter_sets_rejected() -> None:
    ch = _make_chapter(0)
    a = _make_asset("a1", status="in_review")
    _register(a, [ch])
    result = gen.reject_chapter("a1", ch.id, "需要补充第二节")
    assert result is ch
    assert ch.approval_state == "rejected"
    assert a.approval_state == "rejected"


def test_reject_chapter_records_reason_in_history() -> None:
    ch = _make_chapter(0)
    _register(_make_asset("a1", status="in_review"), [ch])
    gen.reject_chapter("a1", ch.id, "缺细节")
    assert len(ch.regeneration_history) == 1
    assert "REJECT" in ch.regeneration_history[0]["instruction"]


def test_submit_asset_for_review_moves_status() -> None:
    chs = [_make_chapter(0), _make_chapter(1)]
    chs[0].approval_state = "rejected"   # 之前 reject 过
    a = _make_asset("a1", status="draft")
    _register(a, chs)
    result = gen.submit_asset_for_review("a1")
    assert result is a
    assert a.status == "in_review"
    # 所有 chapter approval_state 重置为 pending
    assert all(c.approval_state == "pending" for c in chs)


def test_submit_asset_missing_returns_none() -> None:
    assert gen.submit_asset_for_review("a-fake") is None


# ─── T11 发布 ──────────────────────────────────────────────────────


def test_publish_asset_internal_creates_record() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    records = gen.publish_asset(
        "a1", destinations=["internal"], publish_mode="full",
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.destination == "internal"
    assert rec.url and rec.url.startswith("/internal/assets/a1")
    assert rec.status == "success"


def test_publish_asset_multiple_destinations() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    records = gen.publish_asset(
        "a1", destinations=["internal", "export_md"], publish_mode="full",
    )
    assert len(records) == 2
    dests = {r.destination for r in records}
    assert dests == {"internal", "export_md"}


def test_publish_asset_public_link_uses_share_url() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    records = gen.publish_asset(
        "a1", destinations=["public_link"], publish_mode="full",
        visibility="team",
    )
    assert records[0].url
    assert "share.tokenknows" in (records[0].url or "")


def test_publish_asset_missing_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        gen.publish_asset("a-fake", ["internal"], "full")


def test_publish_asset_empty_destinations_raises() -> None:
    _register(_make_asset("a1"), [])
    with pytest.raises(ValueError, match="至少选择"):
        gen.publish_asset("a1", [], "full")


def test_publish_asset_invalid_destination_raises() -> None:
    _register(_make_asset("a1"), [])
    with pytest.raises(ValueError, match="未知 destination"):
        gen.publish_asset("a1", ["smoke_signals"], "full")


def test_publish_asset_invalid_mode_raises() -> None:
    _register(_make_asset("a1"), [])
    with pytest.raises(ValueError, match="publish_mode"):
        gen.publish_asset("a1", ["internal"], "yolo")


def test_get_publish_record_returns_none_for_missing() -> None:
    assert gen.get_publish_record("pub-fake") is None


def test_get_publish_record_returns_after_publish() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    records = gen.publish_asset("a1", ["internal"], "full")
    rec_id = records[0].id
    found = gen.get_publish_record(rec_id)
    assert found is records[0]


def test_list_publish_records_for_asset() -> None:
    _register(_make_asset("a1"), [_make_chapter(0)])
    gen.publish_asset("a1", ["internal"], "full")
    gen.publish_asset("a1", ["public_link"], "full")
    records = gen.list_publish_records_for_asset("a1")
    assert len(records) == 2


# ─── delete + clone ───────────────────────────────────────────────


def test_delete_asset_removes_all_state(monkeypatch: pytest.MonkeyPatch) -> None:
    # 跳过 SQLite 真删
    monkeypatch.setattr(gen.get_db(), "delete_asset", lambda _: None)
    _register(_make_asset("a1"), [_make_chapter(0)])
    gen._progress["a1"] = gen._initial_progress("a1")
    assert gen.delete_asset("a1") is True
    assert "a1" not in gen._assets
    assert "a1" not in gen._chapters


def test_delete_asset_missing_returns_false() -> None:
    assert gen.delete_asset("a-fake") is False


def test_clone_asset_creates_new_id() -> None:
    chs = [_make_chapter(0), _make_chapter(1)]
    _register(_make_asset("a1"), chs)
    cloned = gen.clone_asset("a1")
    assert cloned is not None
    assert cloned.id != "a1"
    assert cloned.id.startswith("asset-")
    assert cloned.status == "draft"
    assert cloned.current_version == 1
    # 章节也克隆了
    cloned_chs = gen._chapters[cloned.id]
    assert len(cloned_chs) == 2


def test_clone_asset_missing_returns_none() -> None:
    assert gen.clone_asset("a-fake") is None


# ─── helpers · _pick_diverse_events / _initial_progress / _stage_index ─


def test_initial_progress_5_stages() -> None:
    p = gen._initial_progress("a1")
    assert p.asset_id == "a1"
    assert p.overall_status == "pending"
    assert len(p.stages) == 5
    names = [s.name for s in p.stages]
    assert names == ["collect", "outline", "content", "evidence", "assess"]


def test_stage_index() -> None:
    p = gen._initial_progress("a1")
    assert gen._stage_index(p, "outline") == 1
    assert gen._stage_index(p, "assess") == 4
    with pytest.raises(ValueError):
        gen._stage_index(p, "missing")  # type: ignore[arg-type]


def test_pick_diverse_events_rotates_sources() -> None:
    by_source = {
        "github": [{"id": "g1"}, {"id": "g2"}, {"id": "g3"}],
        "claude_code": [{"id": "c1"}, {"id": "c2"}],
    }
    picked = gen._pick_diverse_events(by_source, num=4)
    assert len(picked) == 4
    # 应该 round-robin: g1, c1, g2, c2
    ids = [e["id"] for e in picked]
    assert "g1" in ids and "c1" in ids and "g2" in ids


def test_pick_diverse_events_handles_empty() -> None:
    assert gen._pick_diverse_events({}, num=4) == []


def test_pick_diverse_events_caps_at_num() -> None:
    by_source = {
        "github": [{"id": f"g{i}"} for i in range(10)],
    }
    picked = gen._pick_diverse_events(by_source, num=3)
    assert len(picked) == 3
