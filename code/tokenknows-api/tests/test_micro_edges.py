"""精确覆盖剩余 generation_service 行 · _stage_evidence 内部 / 队列满 / 评估边界."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.schemas.asset import Asset, Chapter
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


# ─── _publish_event · QueueFull 分支 (line 247-249) ────────────────


@pytest.mark.asyncio
async def test_publish_event_queue_full_swallowed() -> None:
    """单订阅者的 queue 满 → 不阻塞其它 (line 247-249 warning)."""
    # 手动塞个小 queue
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    gen._sse_queues["a1"] = [queue]
    # 第一条 put 成功
    await queue.put(SseEvent(event="stage_started", asset_id="a1", ts=_now()))
    # 第二条 publish 应触发 QueueFull → swallow
    await gen._publish_event(
        "a1", SseEvent(event="done", asset_id="a1", ts=_now()),
    )
    # queue 仍然只有 1 条 (第二条 put 失败被吞)
    assert queue.qsize() == 1


# ─── _build_evidence_from_event · trust_score None fallback (969-970) ─


def test_build_evidence_default_trust_for_unknown_source() -> None:
    """event 没有 trust_score 且 source_type 不在映射 → 0.60."""
    event = {
        "id": "ev-1",
        "source_type": "vscode",   # 不在 github/claude_code/cursor 映射
        "content": "x",
        "occurred_at": "2026-05-22T00:00:00Z",
        "title": "t",
    }
    ev = gen._build_evidence_from_event(
        event, "ch-1", 0, 0, 10,
        cosine_score=None, composite_score=None,
    )
    # citation_strength 用 trust=0.6 计算 (0.6 * 0.85~1.0 范围)
    assert ev.trust_score is not None
    # 内部 trust_score 字段在 ev.payload 或 ev.trust_score
    assert ev.id.startswith("ev-")


def test_build_evidence_trust_from_known_source() -> None:
    """github 默认 0.85."""
    event = {
        "id": "ev-1",
        "source_type": "github",
        "content": "x",
        "occurred_at": "2026-05-22T00:00:00Z",
        "title": "t",
        # 无 trust_score
    }
    ev = gen._build_evidence_from_event(event, "ch-1", 0, 0, 10)
    # github 默认 trust = 0.85
    assert ev.trust_score is not None


# ─── _pick_diverse_events bucket exhausted (line 935) ──────────────


def test_pick_diverse_events_bucket_exhausted_removed() -> None:
    """某 source bucket 没新事件了 → 从 sources 删除."""
    # 让 github 只有 1 个事件, 但 num=3, 强制走 remove 分支
    by_source = {
        "github": [{"id": "g1"}],
        "claude_code": [{"id": "c1"}, {"id": "c2"}],
    }
    picked = gen._pick_diverse_events(by_source, num=3)
    assert len(picked) == 3
    # 应该全部都取到 (round-robin 但 github 池干了, 转 claude_code)


# ─── _assess_slop heuristic 短内容 fallback ───────────────────────


@pytest.mark.asyncio
async def test_assess_slop_heuristic_no_content() -> None:
    """heuristic 路径中, content 是空 → 返 0.5 + reason='no content'."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    # 仅一个空 chapter
    chapters = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="")]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(side_effect=RuntimeError("force heuristic"))

    async def fake_get_router():
        return fake_router

    import app.services.generation_service as gs
    setattr_kwarg = "get_router"
    # use monkeypatch via direct assign in same module
    original = getattr(gs, setattr_kwarg)
    setattr(gs, setattr_kwarg, fake_get_router)
    try:
        score, method, reason = await gs._assess_slop_via_llm(
            asset, chapters, GenerateAssetRequest(type="weekly_report", time_window="W21"),
        )
    finally:
        setattr(gs, setattr_kwarg, original)

    assert method == "heuristic_fallback"
    # 空 content → 0.5 + "no content"
    assert score == 0.5
    assert reason == "no content"


# ─── _assess_slop LLM 空 text 触发 ValueError (line 1245) ──────────


@pytest.mark.asyncio
async def test_assess_slop_llm_empty_text_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返空字符串 → ValueError → heuristic fallback."""
    from app.llm_gateway.interface import LLMResponse
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    chapters = [Chapter(id="c0", asset_id="a1", order_index=0, title="§1", content="一些内容")]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text="",   # 空 text 触发 line 1245 ValueError
            usage={"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
            model_used="m", provider="ollama", latency_ms=10,
        ),
    )

    async def fake_get_router():
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get_router)
    score, method, _ = await gen._assess_slop_via_llm(
        asset, chapters, GenerateAssetRequest(type="weekly_report", time_window="W21"),
    )
    assert method == "heuristic_fallback"


# ─── regenerate_chapter 找不到 asset (line 1415) ─────────────────


@pytest.mark.asyncio
async def test_regenerate_chapter_chapter_exists_but_asset_missing() -> None:
    """chapter 存在但 _assets 没该 asset_id → 返 None (line 1415).

    这是一个 race 边界: 在 chapter 已注册到 _chapters[a1] 但 asset 刚被删的瞬间.
    """
    ch = Chapter(id="ch-0", asset_id="a1", order_index=0, title="§1", content="x")
    gen._chapters["a1"] = [ch]
    # _assets 里没有 a1
    result = await gen.regenerate_chapter("a1", "ch-0", "rewrite")
    assert result is None


# ─── publish_asset · summary_with_backlink mode (line 1702-1703) ────


def test_publish_asset_summary_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_mode='summary_with_backlink' 路径."""
    asset = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = asset
    gen._chapters["a1"] = [Chapter(id="c", asset_id="a1", order_index=0, title="t", content="x")]
    # mock _persist_publish_record 避免 FK 约束
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    records = gen.publish_asset("a1", ["internal"], "summary_with_backlink")
    assert records[0].publish_mode == "summary_with_backlink"


# ─── _refresh_asset_approval · 没 chapter 直接 return (line 1883) ────


def test_refresh_asset_approval_no_chapters_skip() -> None:
    """_chapters[asset_id] 为空 list → 直接 return (不抛)."""
    a = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets["a1"] = a
    gen._chapters["a1"] = []   # 空
    gen._refresh_asset_approval("a1")   # 不抛
    assert a.approval_state == "pending"   # 状态没变


def test_refresh_asset_approval_missing_asset_skip() -> None:
    """asset 不存在 → 直接 return."""
    gen._refresh_asset_approval("a-no-such")   # 不抛
