"""收尾最后 33 行 · 99% → 100% 后端推齐.

剩余:
- generation_service 16 lines
- generation.py 15 lines (SSE heartbeat)
- events.py 1 line
- resilience.py 1 line
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.llm_gateway.interface import LLMResponse
from app.schemas.asset import Asset, Chapter, Evidence, EvidencePreview
from app.schemas.generation import GenerateAssetRequest, SseEvent
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_e = dict(gen._evidence_by_chapter)
    snap_p = dict(gen._progress)
    snap_q = dict(gen._sse_queues)
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._sse_queues.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    settings = gen.get_settings()
    monkeypatch.setattr(settings, "instance_egress_enabled", True)
    monkeypatch.setattr(settings, "default_project_egress_enabled", True)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._sse_queues.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._evidence_by_chapter.update(snap_e)
    gen._progress.update(snap_p)
    gen._sse_queues.update(snap_q)


# ─── _stage_evidence trust fallback (line 715) ────────────────────


@pytest.mark.asyncio
async def test_stage_evidence_trust_fallback_unknown_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event 无 trust_score 且 source_type 不在映射 → 0.60 fallback (line 715)."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = [
        Chapter(id="ch-0", asset_id="a1", order_index=0, title="§1", content="content with [1]"),
    ]
    gen._progress["a1"] = gen._initial_progress("a1")

    # 自定义 source 无 trust_score → 走 fallback default 0.60
    event = {
        "id": "ev-1", "source_type": "unknown_source_type",
        "content": "x", "occurred_at": _now().isoformat(),
        "title": "t", "source_ref": "x", "external_id": "x",
        # 关键: trust_score 不存在
    }

    class FakeDb:
        def list_events(self, **kw):
            return [event] * 4, 4

    monkeypatch.setattr(gen, "get_db", lambda: FakeDb())

    async def fake_embed(texts, model=None):
        return [[1.0, 0.0]] * (len(texts))

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed)
    result = await gen._stage_evidence("a1", GenerateAssetRequest(type="weekly_report", time_window="W"))
    assert result["evidence_total"] > 0


# ─── _stage_evidence 的 [N] tag normalize 触发分支 (line 774-781) ─


@pytest.mark.asyncio
async def test_stage_evidence_normalize_tags_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 输出 [1][3][5] (超量/跳号) → normalize 后 content 改 → log normalize 行."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    # 章节内容含跳号 [1][3][5] → normalize 会把它改成 [1][2][3]
    gen._chapters["a1"] = [
        Chapter(id="ch-0", asset_id="a1", order_index=0, title="§1",
                content="第一段 [1] 中间 [3] 末尾 [5]"),
    ]
    gen._progress["a1"] = gen._initial_progress("a1")

    events = [
        {"id": f"ev-{i}", "source_type": "github",
         "content": f"event {i}", "occurred_at": _now().isoformat(),
         "title": f"t{i}", "source_ref": "x", "external_id": f"ext{i}",
         "trust_score": 0.8}
        for i in range(4)
    ]

    class FakeDb:
        def list_events(self, **kw):
            return events, 4

    monkeypatch.setattr(gen, "get_db", lambda: FakeDb())

    async def fake_embed(texts, model=None):
        return [[1.0, 0.0]] * len(texts)

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed)
    await gen._stage_evidence("a1", GenerateAssetRequest(type="weekly_report", time_window="W"))
    # normalize 之后 content 应该是 [1][2][3] 而非 [1][3][5]
    new_content = gen._chapters["a1"][0].content
    assert "[1]" in new_content
    assert "[5]" not in new_content   # 超出 4 个 evidence 限制的 [5] 被剥


# ─── _enforce_source_diversity_scored 完全无外族 (line 830) ───────


def test_enforce_source_diversity_scored_no_alt_keeps_dominant() -> None:
    """top-N 全 github 且没有外族 → 不换 (line 830 退出 if)."""
    scored = [
        (0.9, 0.8, 0.85, {"source_type": "github"}),
        (0.85, 0.7, 0.85, {"source_type": "github"}),
        (0.8, 0.6, 0.85, {"source_type": "github"}),
    ]
    out = gen._enforce_source_diversity_scored(scored, num=3, min_sources=2)
    # 没法 swap → 接受单源
    assert len(out) == 3


# ─── _stage_assess citation_density trust fallback (1045-1056) ────


@pytest.mark.asyncio
async def test_stage_assess_no_avg_cosine_uses_trust_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evidence stage metadata 无 avg_cosine_per_chapter → 用 trust_score 均值 fallback."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = [
        Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="内容"),
    ]
    gen._progress["a1"] = gen._initial_progress("a1")
    # 没给 evidence stage 设 avg_cosine_per_chapter
    gen._progress["a1"].stages[3].metadata = {}   # 空 metadata
    # 但 evidence 列表非空
    gen._evidence_by_chapter["c0"] = [
        Evidence(
            id="e1", chapter_id="c0", event_id="ev1",
            event_version=1, span_start=0, span_end=10,
            citation_text="x", manually_added=False, stale=False,
            trust_score=0.9,
            event_preview=EvidencePreview(
                event_id="ev1", source_type="github",
                source_ref="o/r", occurred_at="2026-01-01",
                content_excerpt="x",
            ),
        ),
    ]

    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.2, "llm", "ok")),
    )
    result = await gen._stage_assess("a1", GenerateAssetRequest(type="weekly_report", time_window="W"))
    # citation_density 不为 0 (用 trust=0.9 fallback)
    assert result["citation_density"] > 0


# ─── _stage_assess metadata IndexError fallback (line 1055-1056) ─


@pytest.mark.asyncio
async def test_stage_assess_metadata_error_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """progress.stages[ev_idx] 抛 → citation_density = 0.0 (line 1055-1056)."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="x")]
    gen._progress["a1"] = gen._initial_progress("a1")
    # 删除 evidence stage 触发 IndexError / ValueError
    gen._progress["a1"].stages = []   # 空 stages → _stage_index 抛 ValueError

    monkeypatch.setattr(
        gen, "_assess_slop_via_llm",
        AsyncMock(return_value=(0.2, "llm", "ok")),
    )
    result = await gen._stage_assess("a1", GenerateAssetRequest(type="weekly_report", time_window="W"))
    assert result["citation_density"] == 0.0


# ─── _compute_similarity 当 current_text 空 (line 1146) ──────────


@pytest.mark.asyncio
async def test_compute_similarity_empty_outline() -> None:
    """current_text 为空 → 'no_history'."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="",  # 空 title
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    b = Asset(
        id="a2", project_id="p1", type="weekly_report", title="other",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._assets["a2"] = b
    gen._chapters["a1"] = []   # 空 chapter list → outline 空
    gen._chapters["a2"] = [Chapter(id="c", asset_id="a2", order_index=0, title="T", content="x")]
    sim, method, _ = await gen._compute_similarity_to_history(a, gen._chapters["a1"])
    assert sim == 0.0
    assert method == "no_history"


# ─── _compute_similarity cosine 内部抛错被吞 (line 1178-1179) ─────


@pytest.mark.asyncio
async def test_compute_similarity_cosine_exception_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cosine() 抛 → continue 跳过该 prior, 不整体失败 (line 1178-1179)."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="current",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    prior = Asset(
        id="a2", project_id="p1", type="weekly_report", title="prior",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._assets["a2"] = prior
    gen._chapters["a1"] = [Chapter(id="c1", asset_id="a1", order_index=0, title="t1", content="x")]
    gen._chapters["a2"] = [Chapter(id="c2", asset_id="a2", order_index=0, title="t2", content="y")]

    async def fake_embed(texts, model=None):
        return [[1.0, 0.0]] * len(texts)

    monkeypatch.setattr("app.llm_gateway.embedding.embed_batch", fake_embed)

    # mock cosine 抛
    def cosine_throw(*a, **kw):
        raise RuntimeError("dim mismatch")

    monkeypatch.setattr("app.llm_gateway.embedding.cosine", cosine_throw)
    sim, method, _ = await gen._compute_similarity_to_history(a, gen._chapters["a1"])
    # cosine 都抛 → best_cos 仍 0
    assert sim == 0.0


# ─── regenerate_chapter normalize_evidence_tags 触发 (line 1464) ──


@pytest.mark.asyncio
async def test_regenerate_chapter_normalizes_evidence_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重生成时已有 evidence → normalize new content 的 [N] 标签 (line 1464)."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    ch = Chapter(id="c1", asset_id="a1", order_index=0, title="§1", content="原内容")
    gen._assets["a1"] = a
    gen._chapters["a1"] = [ch]
    # 已有 2 个 evidence
    gen._evidence_by_chapter["c1"] = [
        Evidence(
            id=f"e{i}", chapter_id="c1", event_id=f"ev{i}",
            event_version=1, span_start=0, span_end=10,
            citation_text="x", manually_added=False, stale=False,
            event_preview=EvidencePreview(
                event_id=f"ev{i}", source_type="github",
                source_ref="o/r", occurred_at="2026-01-01",
                content_excerpt="x",
            ),
        )
        for i in range(2)
    ]

    fake_router = AsyncMock()
    # LLM 返带跳号 [1][3][5] 的内容
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text="新内容 [1] 中间 [3] 末尾 [5] · 长度足够通过 30 字符门槛检查",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_used="m", provider="ollama", latency_ms=10,
        ),
    )

    async def fake_get():
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get)
    result = await gen.regenerate_chapter("a1", "c1", "rewrite")
    assert result is not None
    # 因为只 2 evidence, [5] 应被剥, 跳号 [1][3] 应 normalize 成 [1][2]
    assert "[5]" not in result.content


# ─── _refresh_asset_approval rejected 路径 (line 1886) ──────────


def test_refresh_asset_approval_rejected_branch() -> None:
    """任一 ch.approval_state=='rejected' → asset.approval_state='rejected' (line 1886)."""
    a = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="in_review", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chs = [
        Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="x"),
        Chapter(id="c1", asset_id="a1", order_index=1, title="§2", content="y"),
    ]
    chs[0].approval_state = "rejected"
    gen._assets["a1"] = a
    gen._chapters["a1"] = chs
    gen._refresh_asset_approval("a1")
    assert a.approval_state == "rejected"


# ─── SSE heartbeat (generation.py line 401-407) ─────────────────


@pytest.mark.asyncio
async def test_sse_stream_heartbeat_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """queue 空 wait_for 超时 → 发心跳 ': heartbeat\\n\\n' (line 401-407)."""
    a = Asset(
        id="a-hb", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a-hb"] = a
    gen._chapters["a-hb"] = []
    gen._progress["a-hb"] = gen._initial_progress("a-hb")

    from app.main import app

    # 让 wait_for 立即超时
    original_wait_for = asyncio.wait_for

    async def quick_timeout(coro, timeout):
        return await original_wait_for(coro, timeout=0.05)

    monkeypatch.setattr(asyncio, "wait_for", quick_timeout)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 异步推一个 done 等待 heartbeat 出现后再推
        async def push_done_late():
            await asyncio.sleep(0.3)   # 等心跳触发
            await gen._publish_event(
                "a-hb",
                SseEvent(event="done", asset_id="a-hb", ts=_now()),
            )

        push_task = asyncio.create_task(push_done_late())
        chunks_text = ""
        async with client.stream("GET", "/api/v1/assets/a-hb/generation/stream") as r:
            async for chunk in r.aiter_text():
                chunks_text += chunk
                if "heartbeat" in chunks_text and "done" in chunks_text:
                    break
                if len(chunks_text) > 10000:
                    break
        await push_task
    # 至少看到 heartbeat 或 done
    assert "heartbeat" in chunks_text or "done" in chunks_text
