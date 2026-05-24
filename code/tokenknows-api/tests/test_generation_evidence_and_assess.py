"""_stage_evidence + _assess_slop_via_llm · 集成测试 (mock embed + LLM).

_stage_evidence 流程:
  1. db.list_events → 取项目近 30 天事件
  2. embed_batch(events + chapters) 合并 batch
  3. 每章 cosine top-4, 强制 ≥2 source_type
  4. 没事件 fallback / embedding 失败 fallback
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.llm_gateway.interface import LLMResponse
from app.schemas.asset import Asset, Chapter
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _setup(asset_id: str = "a1", chapters: int = 2) -> Asset:
    a = Asset(
        id=asset_id, project_id="p1", type="weekly_report",
        title="周报", status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets[asset_id] = a
    gen._chapters[asset_id] = [
        Chapter(
            id=f"ch-{i}", asset_id=asset_id, order_index=i,
            title=f"§{i+1}", content=f"chapter {i} content",
        )
        for i in range(chapters)
    ]
    gen._progress[asset_id] = gen._initial_progress(asset_id)
    return a


def _req() -> GenerateAssetRequest:
    return GenerateAssetRequest(type="weekly_report", time_window="2026-W21")


# ─── _stage_evidence ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_evidence_no_events_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """db 没事件 → 返回 fallback reason."""
    _setup("a1")

    class EmptyDb:
        def list_events(self, **kw):
            return [], 0

    monkeypatch.setattr(gen, "get_db", lambda: EmptyDb())
    result = await gen._stage_evidence("a1", _req())
    assert result["evidence_total"] == 0
    assert result["fallback_used"] is True
    assert "no events" in result.get("reason", "")


@pytest.mark.asyncio
async def test_stage_evidence_no_chapters_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asset 没 chapter → return zero."""
    _setup("a1", chapters=0)

    class HasEventsDb:
        def list_events(self, **kw):
            return [{"id": "ev-1", "source_type": "github",
                     "content": "x", "occurred_at": _now().isoformat(),
                     "title": "t", "trust_score": 0.9,
                     "source_ref": "o/r", "external_id": "ext"}], 1

    monkeypatch.setattr(gen, "get_db", lambda: HasEventsDb())
    result = await gen._stage_evidence("a1", _req())
    assert result["evidence_total"] == 0


@pytest.mark.asyncio
async def test_stage_evidence_with_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常路径: events + chapters embed + 选 top-4."""
    _setup("a1", chapters=1)
    fake_events = []
    for i in range(6):
        fake_events.append({
            "id": f"ev-{i}",
            "source_type": "github" if i % 2 == 0 else "claude_code",
            "content": f"event {i} content",
            "occurred_at": _now().isoformat(),
            "title": f"event {i}",
            "trust_score": 0.8,
            "source_ref": "o/r",
            "external_id": f"ext-{i}",
            "author": {"name": "alice", "email": "a@b.com"},
            "external_url": "https://github.com/o/r/pull/1",
        })

    class FakeDb:
        def list_events(self, **kw):
            return fake_events, len(fake_events)

    monkeypatch.setattr(gen, "get_db", lambda: FakeDb())

    # mock embed_batch return: 6 events + 1 chapter = 7 vectors
    fake_vectors = [[1.0, 0.0]] * 6 + [[1.0, 0.0]]  # 全部对齐 cosine=1

    async def fake_embed(texts, model=None):
        return fake_vectors

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed)
    result = await gen._stage_evidence("a1", _req())
    assert result["evidence_total"] > 0
    assert result["chapters_with_evidence"] >= 1


@pytest.mark.asyncio
async def test_stage_evidence_embedding_fail_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """embedding 调用失败 → fallback 到 round-robin."""
    _setup("a1", chapters=1)
    fake_events = [{
        "id": f"ev-{i}", "source_type": "github" if i % 2 == 0 else "claude_code",
        "content": f"c{i}", "occurred_at": _now().isoformat(),
        "title": f"t{i}", "trust_score": 0.8, "source_ref": "o/r",
        "external_id": f"e{i}", "author": {"name": "a"},
        "external_url": None,
    } for i in range(4)]

    class FakeDb:
        def list_events(self, **kw):
            return fake_events, len(fake_events)

    monkeypatch.setattr(gen, "get_db", lambda: FakeDb())
    from app.llm_gateway.embedding import EmbeddingError

    async def fake_embed_fail(texts, model=None):
        raise EmbeddingError("ollama down")

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed_fail)
    result = await gen._stage_evidence("a1", _req())
    # fallback path 仍产生 evidence
    assert result["evidence_total"] > 0


# ─── T132 · time_window 透传到 db.list_events ─────────────────────


@pytest.mark.asyncio
async def test_stage_evidence_respects_request_time_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T132 旧版硬编码 30 天忽略 req.time_window; 现在应根据 time_window
    传不同 from_iso 给 db.list_events."""
    _setup("a1", chapters=0)  # no chapters → 走早期 return, 只验 db 调用参数

    captured: dict[str, str] = {}

    class CapturingDb:
        def list_events(self, **kw):
            captured["from_iso"] = kw.get("from_iso", "")
            captured["limit"] = kw.get("limit", 0)
            # 必须返非空 events, 否则走 no_events fallback 不进 chapters 检查
            return [{
                "id": "ev-1", "source_type": "github",
                "content": "x", "occurred_at": _now().isoformat(),
                "title": "t", "trust_score": 0.9,
                "source_ref": "o/r", "external_id": "ext",
            }], 1

    monkeypatch.setattr(gen, "get_db", lambda: CapturingDb())

    # 跑 this_week (7 天窗口)
    req_7d = GenerateAssetRequest(type="weekly_report", time_window="this_week")
    await gen._stage_evidence("a1", req_7d)
    iso_7d = captured["from_iso"]

    # 跑 last_30_days (30 天窗口)
    req_30d = GenerateAssetRequest(type="weekly_report", time_window="last_30_days")
    await gen._stage_evidence("a1", req_30d)
    iso_30d = captured["from_iso"]

    # UTC ISO 字典序 = 时间序; 30 天前比 7 天前早 → 字符串更小
    assert iso_30d < iso_7d, f"30d window should produce earlier from_iso: {iso_30d!r} >= {iso_7d!r}"
    # limit 仍是 300 (没改业务参数)
    assert captured["limit"] == 300


@pytest.mark.asyncio
async def test_stage_evidence_metadata_includes_time_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """所有 return path 都应在 metadata 带 time_window (debug 一致性)."""
    _setup("a1", chapters=0)

    class EmptyDb:
        def list_events(self, **kw):
            return [], 0

    monkeypatch.setattr(gen, "get_db", lambda: EmptyDb())
    req = GenerateAssetRequest(type="adr", time_window="last_14_days")
    result = await gen._stage_evidence("a1", req)
    assert result.get("time_window") == "last_14_days"


# ─── _assess_slop_via_llm ────────────────────────────────────────


@pytest.mark.asyncio
async def test_assess_slop_no_chapters_short_circuit() -> None:
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    score, method, reasoning = await gen._assess_slop_via_llm(asset, [], _req())
    assert score == 0.0
    assert method == "no_chapters"


@pytest.mark.asyncio
async def test_assess_slop_llm_success_returns_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [
        Chapter(id="ch-0", asset_id="a1", order_index=0, title="§1", content="x" * 200)
    ]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text='{"slop_score": 0.25, "reasoning": "套话不多, 主体扎实"}',
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            model_used="m", provider="ollama", latency_ms=200,
        ),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    score, method, reasoning = await gen._assess_slop_via_llm(asset, chapters, _req())
    assert score == 0.25
    assert method == "llm"
    assert "套话" in reasoning


@pytest.mark.asyncio
async def test_assess_slop_llm_json_in_markdown_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 把 JSON 包在 ```json ... ``` 里 → 容错抽出."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="x")]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text='```json\n{"slop_score": 0.4, "reasoning": "ok"}\n```',
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_used="m", provider="ollama", latency_ms=100,
        ),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    score, method, _ = await gen._assess_slop_via_llm(asset, chapters, _req())
    assert score == 0.4
    assert method == "llm"


@pytest.mark.asyncio
async def test_assess_slop_llm_invalid_json_fallback_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返非 JSON → 启发式 (套话词频)."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [
        Chapter(
            id="c0", asset_id="a1", order_index=0, title="§1",
            content="本周积极推进各项工作, 我们将持续优化, 进一步深入" * 5,
        ),
    ]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text="not json at all",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_used="m", provider="ollama", latency_ms=100,
        ),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    score, method, _ = await gen._assess_slop_via_llm(asset, chapters, _req())
    assert method == "heuristic_fallback"
    assert score > 0.2   # 套话密集 → slop 应该高


@pytest.mark.asyncio
async def test_assess_slop_llm_router_exception_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """router 抛异常 → heuristic fallback."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="干净内容")]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(side_effect=RuntimeError("network"))

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    score, method, _ = await gen._assess_slop_via_llm(asset, chapters, _req())
    assert method == "heuristic_fallback"
    assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_assess_slop_clamps_to_0_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 返超范围 score → clamp."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="x")]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text='{"slop_score": 5.0, "reasoning": "way too high"}',
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_used="m", provider="ollama", latency_ms=100,
        ),
    )

    async def fake_get() -> object:
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    score, method, _ = await gen._assess_slop_via_llm(asset, chapters, _req())
    assert score == 1.0   # clamped
    assert method == "llm"
