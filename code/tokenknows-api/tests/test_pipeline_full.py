"""_run_pipeline 全流程 happy path · mock 所有 5 阶段."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.schemas.asset import Asset
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service as gen


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
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._progress.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._progress.update(snap_p)


@pytest.mark.asyncio
async def test_run_pipeline_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """5 阶段全 mock 成功 → asset.status=done."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._progress["a1"] = gen._initial_progress("a1")

    # mock 5 个 stage 各自返 metadata
    monkeypatch.setattr(gen, "_stage_collect", AsyncMock(return_value={"x": 1}))
    monkeypatch.setattr(gen, "_stage_outline", AsyncMock(return_value={"titles": ["§1"]}))
    monkeypatch.setattr(gen, "_stage_content", AsyncMock(return_value={"chapters_completed": 1}))
    monkeypatch.setattr(gen, "_stage_evidence", AsyncMock(return_value={"evidence_total": 4}))
    monkeypatch.setattr(gen, "_stage_assess", AsyncMock(return_value={
        "coverage": 1.0, "citation_density": 0.5,
        "slop_score": 0.2, "similarity": 0.0,
    }))

    req = GenerateAssetRequest(type="weekly_report", time_window="W21")
    await gen._run_pipeline("a1", req)

    p = gen._progress["a1"]
    assert p.overall_status == "done"
    assert p.current_stage is None


@pytest.mark.asyncio
async def test_run_pipeline_stage_failure_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """某阶段抛 → pipeline 短路, 不调后续阶段."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._progress["a1"] = gen._initial_progress("a1")

    collect_calls = []
    outline_calls = []
    content_calls = []

    async def fake_collect(*a, **kw):
        collect_calls.append(True)
        return {}

    async def fake_outline(*a, **kw):
        outline_calls.append(True)
        raise RuntimeError("LLM down")

    async def fake_content(*a, **kw):
        content_calls.append(True)
        return {}

    monkeypatch.setattr(gen, "_stage_collect", fake_collect)
    monkeypatch.setattr(gen, "_stage_outline", fake_outline)
    monkeypatch.setattr(gen, "_stage_content", fake_content)

    req = GenerateAssetRequest(type="weekly_report", time_window="W21")
    await gen._run_pipeline("a1", req)   # 应该不抛 (except 捕获)

    assert len(collect_calls) == 1
    assert len(outline_calls) == 1
    assert len(content_calls) == 0   # 短路了
    # overall_status 应该 failed (由 _run_stage 设)
    assert gen._progress["a1"].overall_status == "failed"
