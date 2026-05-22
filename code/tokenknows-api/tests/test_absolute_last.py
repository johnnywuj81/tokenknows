"""绝对最后 10 行 · 99.5 → 100%."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.asset import Asset, Chapter, EvidencePreview
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_p = dict(gen._publish_records)
    gen._assets.clear()
    gen._chapters.clear()
    gen._publish_records.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._publish_records.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._publish_records.update(snap_p)


# ─── _enforce_source_diversity_scored empty (line 830) ─────────


def test_enforce_source_diversity_scored_empty_returns_empty() -> None:
    """scored=[] → []."""
    assert gen._enforce_source_diversity_scored([], num=3) == []


# ─── _pick_diverse_events bucket exhausted removes source (line 935) ──


def test_pick_diverse_events_bucket_seen_ids_path() -> None:
    """bucket 内全部都已 picked (seen_ids 拦) → sources.remove(s) 触发."""
    # 给 github 2 个事件, 都重复 id → picked None → remove(s)
    by_source = {
        "github": [{"id": "g1"}, {"id": "g1"}],   # 同 id 重复
        "claude_code": [{"id": "c1"}],
    }
    picked = gen._pick_diverse_events(by_source, num=3)
    # 第二次轮到 github 时 g1 已 picked, 没新的 → remove github
    assert len(picked) == 2   # 只取到 g1 + c1


# ─── _stage_assess result["_most_similar_asset_id"] (line 1110) ────


@pytest.mark.asyncio
async def test_stage_assess_writes_most_similar_id_when_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 prior asset 且 cosine > 0 → result 含 _most_similar_asset_id."""
    from unittest.mock import AsyncMock
    from app.schemas.generation import GenerateAssetRequest

    a = Asset(
        id="a-cur", project_id="p1", type="weekly_report", title="current",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    prior = Asset(
        id="a-prior", project_id="p1", type="weekly_report", title="prior",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a-cur"] = a
    gen._assets["a-prior"] = prior
    gen._chapters["a-cur"] = [Chapter(id="c1", asset_id="a-cur", order_index=0, title="t", content="x")]
    gen._chapters["a-prior"] = [Chapter(id="c2", asset_id="a-prior", order_index=0, title="t", content="y")]
    gen._progress["a-cur"] = gen._initial_progress("a-cur")

    async def fake_embed(texts, model=None):
        # 让 cos(current, prior) = 1.0
        return [[1.0, 0.0]] * len(texts)

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed)
    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.1, "llm", "good")),
    )
    result = await gen._stage_assess(
        "a-cur", GenerateAssetRequest(type="weekly_report", time_window="W"),
    )
    assert "_most_similar_asset_id" in result
    assert result["_most_similar_asset_id"] == "a-prior"


# ─── publish_asset · unknown destination 实际不可达 但 else 分支 (1702-1703) ──


def test_publish_asset_internal_no_version() -> None:
    """publish_asset 走 export_md / 但 current_version=0 (新 asset)."""
    a = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="generating", current_version=0,   # 0 版本
        template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    # 看代码 1702-1703 是 else 分支 (未知 destination), 但 valid_destinations
    # 校验早就拦截了. 所以 1702-1703 是死代码 — 这里不强求覆盖.
    # 仅验证 publish 不抛
    records = gen.publish_asset("a1", ["internal"], "full")
    assert records[0].url is not None


# ─── BulkheadSemaphore .stats (line 241) ───────────────────────────


def test_bulkhead_stats_property() -> None:
    from app.core.resilience import BulkheadSemaphore
    bh = BulkheadSemaphore("test", max_concurrent=5)
    stats = bh.stats
    assert stats["name"] == "test"
    assert stats["active"] == 0
    assert stats["waiting"] == 0
    assert stats["max_concurrent"] == 5


# ─── events.py line 40 (empty events 详情) ─────────────────────────


def test_ingest_events_400_empty_detail() -> None:
    """空 events 数组 → detail='events 不能为空' (line 37)."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/v1/projects/p/events", json={"events": []})
    assert r.status_code == 400
    assert "不能为空" in r.json()["detail"]
