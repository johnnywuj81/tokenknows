"""5 阶段 stages 集成测试 · mock LLM + embed.

覆盖 _stage_outline / _stage_content / _stage_evidence / _stage_assess
以及 _call_chapter_llm 兜底逻辑.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.llm_gateway.interface import LLMResponse
from app.schemas.asset import Asset, Chapter
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fake_response(text: str = "ok", provider: str = "ollama") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        model_used="m",
        provider=provider,
        latency_ms=100,
    )


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_e = dict(gen._evidence_by_chapter)
    snap_p = dict(gen._progress)
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    settings = gen.get_settings()
    monkeypatch.setattr(settings, "instance_egress_enabled", True)
    monkeypatch.setattr(settings, "default_project_egress_enabled", True)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._evidence_by_chapter.update(snap_e)
    gen._progress.update(snap_p)


def _setup_asset(asset_id: str = "a1") -> Asset:
    a = Asset(
        id=asset_id, project_id="p1", type="weekly_report",
        title="周报", status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets[asset_id] = a
    gen._chapters[asset_id] = []
    gen._progress[asset_id] = gen._initial_progress(asset_id)
    return a


def _req() -> GenerateAssetRequest:
    return GenerateAssetRequest(type="weekly_report", time_window="2026-W21")


# ─── _stage_outline ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_outline_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_asset("a1")
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_fake_response(
            text=json.dumps({"chapters": ["§1", "§2", "§3", "§4", "§5"]}),
        ),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_outline("a1", _req())
    assert result["chapters_total"] == 5
    assert result["titles"] == ["§1", "§2", "§3", "§4", "§5"]
    assert "tokens" in result


@pytest.mark.asyncio
async def test_stage_outline_invalid_json_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 返非法 JSON → fallback 到 _OUTLINE_TEMPLATES."""
    _setup_asset("a1")
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(return_value=_fake_response(text="not json"))

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_outline("a1", _req())
    assert result.get("llm_fallback_to_template") is True
    assert result["chapters_total"] >= 3  # template 有内容


@pytest.mark.asyncio
async def test_stage_outline_too_few_chapters_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_asset("a1")
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_fake_response(text=json.dumps({"chapters": ["only_one"]})),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_outline("a1", _req())
    assert result.get("llm_fallback_to_template") is True


@pytest.mark.asyncio
async def test_stage_outline_router_raises_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_asset("a1")
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(side_effect=RuntimeError("503"))

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_outline("a1", _req())
    assert result.get("llm_fallback_to_template") is True
    assert "503" in (result.get("llm_error") or "")


# ─── _call_chapter_llm 兜底 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_call_chapter_llm_returns_placeholder_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 失败 → 返回 placeholder 内容, 不抛."""
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(side_effect=RuntimeError("LLM down"))

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._call_chapter_llm(
        asset_type="weekly_report",
        title="§1 概述",
        time_window="W21",
        project_id="p1",
        provider="ollama",
        model="x",
    )
    assert "concept" in result or "占位" in result["content"] or "fallback" in result["content"].lower() or "§1 概述" in result["content"]
    assert result["fallback_used"] is True


@pytest.mark.asyncio
async def test_call_chapter_llm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_fake_response(text="## §1\n\n本周完成了 X / Y / Z, 详见 [1]\n"),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._call_chapter_llm(
        asset_type="weekly_report", title="§1", time_window="W21",
        project_id="p1", provider="ollama", model="x",
    )
    assert "本周完成" in result["content"]
    assert result["fallback_used"] is False
    assert result["latency_ms"] >= 0


# ─── _stage_content ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_content_uses_outline_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    """outline 阶段产 titles → content 阶段拿来生成对应章节."""
    a = _setup_asset("a1")
    # 模拟 outline 完成态
    progress = gen._progress["a1"]
    progress.stages[1].metadata = {"titles": ["§A", "§B"]}

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_fake_response(text="本章正文 [1] 参考"),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_content("a1", _req())
    assert result["chapters_completed"] == 2
    chapters = gen._chapters["a1"]
    assert len(chapters) == 2
    assert [c.title for c in chapters] == ["§A", "§B"]


@pytest.mark.asyncio
async def test_stage_content_no_outline_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """没 outline metadata → fallback 用模板."""
    _setup_asset("a1")
    # outline stage 没 titles
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_fake_response(text="正文" * 30),  # 60 字符
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen._stage_content("a1", _req())
    assert result["chapters_completed"] > 0


# ─── _stage_assess (LLM eval) ────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_assess_returns_metrics_with_zero_chapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0 chapter → coverage=0, slop_score 走 heuristic fallback."""
    _setup_asset("a1")
    # _stage_assess 调 _assess_slop_via_llm, mock 它
    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.3, "heuristic_fallback", "fallback")),
    )
    result = await gen._stage_assess("a1", _req())
    assert result["coverage"] == 0.0
    assert result["slop_score"] == 0.3


@pytest.mark.asyncio
async def test_stage_assess_with_chapters_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 chapter + evidence → coverage/citation_density 非 0."""
    _setup_asset("a1")
    gen._chapters["a1"] = [
        Chapter(id="ch-0", asset_id="a1", order_index=0, title="§1", content="x"),
    ]
    # 给 chapter 加 evidence (4 个 → coverage=1.0)
    from app.schemas.asset import Evidence, EvidencePreview
    gen._evidence_by_chapter["ch-0"] = [
        Evidence(
            id=f"e{i}", chapter_id="ch-0", event_id=f"ev{i}",
            event_version=1, span_start=0, span_end=10,
            citation_text="x", manually_added=False, stale=False,
            trust_score=0.8,
            event_preview=EvidencePreview(
                event_id=f"ev{i}", source_type="github",
                source_ref="o/r", occurred_at="2026-05-21T00:00:00Z",
                content_excerpt="x",
            ),
        )
        for i in range(4)
    ]
    # evidence stage metadata 设个空 (用 trust fallback)
    progress = gen._progress["a1"]
    progress.stages[3].metadata = {}

    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.15, "llm", "good")),
    )
    result = await gen._stage_assess("a1", _req())
    assert result["coverage"] == 1.0   # 4/4
    assert result["citation_density"] > 0  # trust_score fallback
    assert result["slop_score"] == 0.15
