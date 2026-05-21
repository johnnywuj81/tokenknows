"""T10 redaction · scan / confirm / exempt / _refresh_redaction_state.

测正则匹配真敏感内容, in-memory state.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.asset import Asset, Chapter
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_asset(asset_id: str = "a1") -> Asset:
    return Asset(
        id=asset_id, project_id="p1", type="weekly_report",
        title="t", status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )


def _make_chapter(idx: int, content: str, asset_id: str = "a1") -> Chapter:
    return Chapter(
        id=f"ch-{idx}", asset_id=asset_id, order_index=idx,
        title=f"§{idx}", content=content,
    )


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_r = dict(gen._redaction_jobs)
    gen._assets.clear()
    gen._chapters.clear()
    gen._redaction_jobs.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._redaction_jobs.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._redaction_jobs.update(snap_r)


def _register(asset: Asset, chapters: list[Chapter]) -> None:
    gen._assets[asset.id] = asset
    gen._chapters[asset.id] = chapters


# ─── scan_redaction ────────────────────────────────────────────────


def test_scan_returns_none_for_no_chapters() -> None:
    """没 chapters → None."""
    _register(_make_asset("a-empty"), [])
    assert gen.scan_redaction("a-empty") is None


def test_scan_detects_email() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "联系 alice@example.com 反馈")])
    job = gen.scan_redaction("a1")
    assert job is not None
    types = {it.type for it in job.items}
    assert "EMAIL" in types


def test_scan_detects_api_key() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "用 sk-proj-abc1234567890abcdefg 测试")])
    job = gen.scan_redaction("a1")
    assert job and any(it.type == "API_KEY" for it in job.items)


def test_scan_detects_ip() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "服务部署在 10.0.0.42")])
    job = gen.scan_redaction("a1")
    assert job and any(it.type == "IP" for it in job.items)


def test_scan_detects_internal() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "对接 Project_Phoenix 客户")])
    job = gen.scan_redaction("a1")
    assert job and any(it.type == "INTERNAL" for it in job.items)


def test_scan_dedups_same_type_text() -> None:
    """同 (type, text) 跨章节只保留 1 个."""
    a = _make_asset("a1")
    _register(a, [
        _make_chapter(0, "a@b.com 出现两次"),
        _make_chapter(1, "a@b.com 又一次"),
    ])
    job = gen.scan_redaction("a1")
    assert job
    emails = [it for it in job.items if it.type == "EMAIL"]
    assert len(emails) == 1


def test_scan_status_done_and_progress_one() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com")])
    job = gen.scan_redaction("a1")
    assert job.status == "done"
    assert job.progress == 1.0


def test_scan_updates_asset_redaction_state_when_hits() -> None:
    a = _make_asset("a1")
    a.redaction_state = "all_confirmed"
    _register(a, [_make_chapter(0, "leak@example.com")])
    gen.scan_redaction("a1")
    assert a.redaction_state == "any_unresolved"


def test_scan_clean_chapter_sets_all_confirmed() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "干净内容, 没敏感词")])
    job = gen.scan_redaction("a1")
    assert job.items == []
    assert a.redaction_state == "all_confirmed"


def test_scan_records_context_before_after() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "before-context test@example.com after-context")])
    job = gen.scan_redaction("a1")
    item = job.items[0]
    assert "before-context" in item.context_before
    assert "after-context" in item.context_after


# ─── confirm / exempt ───────────────────────────────────────────


def test_get_redaction_job_missing() -> None:
    assert gen.get_redaction_job("a-fake") is None


def test_confirm_redaction_marks_items() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com leak@example.com")])
    job = gen.scan_redaction("a1")
    item_ids = [it.id for it in job.items]
    updated = gen.confirm_redaction("a1", item_ids[:1])
    assert updated
    # 第 1 个 confirmed, 第 2 个仍 pending
    statuses = {it.status for it in updated.items}
    assert "confirmed" in statuses
    assert "pending" in statuses


def test_confirm_redaction_missing_job_returns_none() -> None:
    assert gen.confirm_redaction("a-no-scan", ["x"]) is None


def test_confirm_all_items_lifts_redaction_state() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com")])
    job = gen.scan_redaction("a1")
    all_ids = [it.id for it in job.items]
    gen.confirm_redaction("a1", all_ids)
    assert a.redaction_state == "all_confirmed"


def test_exempt_redaction_marks_item_with_reason() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com")])
    job = gen.scan_redaction("a1")
    item_id = job.items[0].id
    updated = gen.exempt_redaction("a1", item_id, "示例数据不真实")
    assert updated
    item = next(it for it in updated.items if it.id == item_id)
    assert item.status == "exempted"
    assert item.reason == "示例数据不真实"


def test_exempt_redaction_missing_job_returns_none() -> None:
    assert gen.exempt_redaction("a-fake", "id", "r") is None


def test_exempt_unknown_item_id_is_noop() -> None:
    """不存在的 item_id 不抛, job 状态不变."""
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com")])
    gen.scan_redaction("a1")
    job = gen.exempt_redaction("a1", "red-totally-fake", "x")
    assert job   # job 仍然返回
    # 所有 items 还在 pending
    assert all(it.status == "pending" for it in job.items)


# ─── _refresh_redaction_state ──────────────────────────────────────


def test_refresh_redaction_state_all_done() -> None:
    a = _make_asset("a1")
    _register(a, [_make_chapter(0, "x@y.com")])
    job = gen.scan_redaction("a1")
    for it in job.items:
        it.status = "confirmed"
    gen._refresh_redaction_state("a1", job)
    assert a.redaction_state == "all_confirmed"


def test_refresh_redaction_state_some_pending() -> None:
    a = _make_asset("a1")
    a.redaction_state = "all_confirmed"
    _register(a, [_make_chapter(0, "x@y.com a@b.com")])
    job = gen.scan_redaction("a1")
    # confirm 1 留 1 pending
    if len(job.items) >= 2:
        job.items[0].status = "confirmed"
    gen._refresh_redaction_state("a1", job)
    assert a.redaction_state == "any_unresolved"


def test_refresh_redaction_state_missing_asset() -> None:
    """asset 不存在 → no-op 不抛."""
    job = gen.scan_redaction("a1") or None
    # 直接构造 job 调用
    from app.schemas.asset import RedactionScanJob
    fake_job = RedactionScanJob(
        job_id="x", asset_id="a-fake", status="done",
        progress=1.0, items=[],
    )
    gen._refresh_redaction_state("a-fake-missing", fake_job)   # 不抛
