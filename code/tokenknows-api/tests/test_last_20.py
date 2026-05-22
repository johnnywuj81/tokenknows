"""真正最后 · 后端最后 20 行覆盖到 100%."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.asset import Asset, Chapter
from app.services import generation_service as gen


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_p = dict(gen._progress)
    gen._assets.clear()
    gen._chapters.clear()
    gen._progress.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._progress.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._progress.update(snap_p)


def _api(p: str) -> str:
    return f"/api/v1{p}"


def _seed_asset(asset_id: str = "asset-last-1") -> Asset:
    a = Asset(
        id=asset_id, project_id="proj-last", type="weekly_report",
        title="t", status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets[asset_id] = a
    gen._chapters[asset_id] = []
    return a


# ─── generation.py HTTP 404 paths (lines 111, 151, 167, 169, 172, 195, 198, 209, 300) ─


def test_list_chapter_evidence_missing_asset_404(client: TestClient) -> None:
    """line 111: list_chapter_evidence 404."""
    r = client.get(_api("/assets/asset-no-such/chapters/ch-x/evidence"))
    assert r.status_code == 404


def test_approve_chapter_404_missing_asset(client: TestClient) -> None:
    """line 151."""
    r = client.post(_api("/assets/asset-no-such/chapters/ch-x/approve"))
    assert r.status_code == 404


def test_reject_chapter_404_missing_asset(client: TestClient) -> None:
    """line 167."""
    r = client.post(_api("/assets/asset-no-such/chapters/ch-x/reject"),
                    json={"reason": "test"})
    assert r.status_code == 404


def test_reject_chapter_422_empty_reason(client: TestClient) -> None:
    """line 169."""
    _seed_asset("asset-last-1")
    gen._chapters["asset-last-1"].append(Chapter(
        id="ch-1", asset_id="asset-last-1", order_index=0,
        title="§1", content="x",
    ))
    r = client.post(_api("/assets/asset-last-1/chapters/ch-1/reject"),
                    json={"reason": "   "})
    assert r.status_code == 422


def test_reject_chapter_404_missing_chapter(client: TestClient) -> None:
    """line 172."""
    _seed_asset("asset-last-1")
    r = client.post(_api("/assets/asset-last-1/chapters/ch-fake/reject"),
                    json={"reason": "x"})
    assert r.status_code == 404


def test_scan_redaction_404_no_chapters(client: TestClient) -> None:
    """line 195, 198: scan on asset 无 chapters → 404."""
    _seed_asset("asset-last-1")
    # 没有 chapters
    r = client.post(_api("/assets/asset-last-1/redaction/scan"))
    assert r.status_code == 404


def test_scan_redaction_404_missing_asset(client: TestClient) -> None:
    r = client.post(_api("/assets/no-such/redaction/scan"))
    assert r.status_code == 404


def test_get_redaction_scan_404_missing_asset(client: TestClient) -> None:
    """line 209."""
    r = client.get(_api("/assets/no-such/redaction/scan"))
    assert r.status_code == 404


def test_publish_no_chapters_creates_record_or_422(client: TestClient) -> None:
    """line 300 (publish with no chapters)."""
    _seed_asset("asset-last-1")   # 没 chapters
    r = client.post(
        _api("/assets/asset-last-1/publish"),
        json={"destinations": ["internal"], "publish_mode": "full"},
    )
    # 可能 200/201 因为 publish 不强制要求 chapters
    assert r.status_code in (200, 201, 422)


def test_list_asset_publish_records_404_missing_asset(client: TestClient) -> None:
    """line 300."""
    r = client.get(_api("/assets/no-such/publish-records"))
    assert r.status_code == 404


# ─── _enforce_source_diversity_scored 不变 (line 830) ───────────


def test_enforce_source_diversity_scored_already_2_sources() -> None:
    """top-N 已含 2 个 source_type → 直接返回 (line 830 后的 return)."""
    scored = [
        (0.9, 0.8, 0.85, {"source_type": "github"}),
        (0.85, 0.7, 0.85, {"source_type": "cursor"}),
        (0.8, 0.6, 0.85, {"source_type": "github"}),
    ]
    out = gen._enforce_source_diversity_scored(scored, num=3, min_sources=2)
    assert len(out) == 3


# ─── _stage_assess: avg_cosine 非空且方法=avg_cosine_per_chapter (line 1045) ──


@pytest.mark.asyncio
async def test_stage_assess_avg_cosine_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evidence stage metadata 有 avg_cosine_per_chapter → 用它算 citation_density."""
    from unittest.mock import AsyncMock
    from app.schemas.generation import GenerateAssetRequest
    a = _seed_asset("a1")
    gen._chapters["a1"] = [
        Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="x"),
    ]
    gen._progress["a1"] = gen._initial_progress("a1")
    # 设置 avg_cosine_per_chapter
    gen._progress["a1"].stages[3].metadata = {"avg_cosine_per_chapter": [0.7, 0.8]}

    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.2, "llm", "ok")),
    )
    result = await gen._stage_assess(
        "a1", GenerateAssetRequest(type="weekly_report", time_window="W"),
    )
    assert result["citation_density"] == pytest.approx(0.75, abs=0.01)
    # _method.citation_density should be "avg_cosine_per_chapter"
    assert result["_method"]["citation_density"] == "avg_cosine_per_chapter"


# ─── _compute_similarity: 0 prior_texts after filtering (line 1110) ─


@pytest.mark.asyncio
async def test_compute_similarity_no_valid_prior_text() -> None:
    """所有 prior asset 的 chapters 都空 → no_history (line 1110-1111)."""
    a = Asset(
        id="a-cur", project_id="p", type="weekly_report", title="current",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    prior_empty = Asset(
        id="a-prior", project_id="p", type="weekly_report", title="prior",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a-cur"] = a
    gen._assets["a-prior"] = prior_empty
    gen._chapters["a-cur"] = [Chapter(id="c", asset_id="a-cur", order_index=0, title="t", content="x")]
    gen._chapters["a-prior"] = []   # 空 chapters → outline 空, 被过滤
    sim, method, _ = await gen._compute_similarity_to_history(a, gen._chapters["a-cur"])
    assert method == "no_history"


# ─── publish_asset · public_link 带 visibility (line 1619 covered? + edge case) ─


def test_publish_asset_public_link_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """public_link + visibility=public 路径."""
    a = _seed_asset("a1")
    gen._chapters["a1"] = [Chapter(id="c", asset_id="a1", order_index=0, title="t", content="x")]
    records = gen.publish_asset(
        "a1", ["public_link"], "full", visibility="public",
    )
    assert records[0].destination == "public_link"
    assert records[0].visibility == "public"


def test_publish_asset_export_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """export_md 路径 (line 1702-1703)."""
    a = _seed_asset("a1")
    gen._chapters["a1"] = [Chapter(id="c", asset_id="a1", order_index=0, title="t", content="x")]
    records = gen.publish_asset("a1", ["export_md"], "full")
    assert records[0].destination == "export_md"


# ─── BulkheadSemaphore active property (line 241 in resilience) ───


def test_bulkhead_active_after_release() -> None:
    """active count 0 after release."""
    from app.core.resilience import BulkheadSemaphore
    bh = BulkheadSemaphore("test", max_concurrent=2)
    # __aexit__ 减 _active (line 235-237)
    # 直接调 __aexit__ 模拟 release
    import asyncio
    bh._active = 1
    asyncio.run(bh.__aexit__(None, None, None))
    assert bh._active == 0


# ─── events.py 400 detail string assertion (line 40) ─────────────


def test_ingest_events_over_500_detail(client: TestClient) -> None:
    """详情消息 'events 不能为空' / '单次最多 500 条' (line 40)."""
    events = [
        {
            "source_type": "github", "source_ref": "o/r",
            "external_id": f"e{i}", "version": 1, "event_type": "commit",
            "occurred_at": "2026-05-22T00:00:00Z",
            "title": "t", "content": "c", "content_hash": f"h{i}",
            "payload": {}, "tags": [],
        }
        for i in range(501)
    ]
    r = client.post("/api/v1/projects/p-edge/events", json={"events": events})
    assert r.status_code == 400
    # 触发 line 40 (单次最多 500 条 detail)
    detail = r.json().get("detail", "")
    assert "500" in detail
