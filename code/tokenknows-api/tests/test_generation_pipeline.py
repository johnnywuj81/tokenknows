"""generation_service · 5 阶段 pipeline + regenerate_chapter integration test.

不真打 LLM/Ollama, 全 mock router.generate + embed_batch + _assess_slop_via_llm.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.llm_gateway.interface import LLMResponse
from app.schemas.asset import Asset, Chapter
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_llm_response(text: str = "## 概述\n\n本周完成 X.\n\n[1] 详情见 PR\n", provider: str = "anthropic") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        model_used="x",
        provider=provider,
        latency_ms=234,
    )


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    """每个 test 隔离全局 state + 跳 SQLite + 关 SSE."""
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
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    # 打开 egress 让 LLM 调用通过
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


# ─── _publish_event / SSE queue ────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_sse_queue_returns_queue() -> None:
    q = await gen.subscribe_sse("a1")
    assert isinstance(q, asyncio.Queue)
    assert "a1" in gen._sse_queues
    assert q in gen._sse_queues["a1"]


@pytest.mark.asyncio
async def test_cleanup_sse_removes_queue() -> None:
    q = await gen.subscribe_sse("a1")
    await gen.cleanup_sse("a1", q)
    assert q not in gen._sse_queues.get("a1", [])


@pytest.mark.asyncio
async def test_publish_event_delivers_to_subscriber() -> None:
    from app.schemas.generation import SseEvent
    q = await gen.subscribe_sse("a1")
    event = SseEvent(event="stage_started", asset_id="a1", stage="collect", ts=_now())
    await gen._publish_event("a1", event)
    received = await asyncio.wait_for(q.get(), timeout=0.5)
    assert received.event == "stage_started"


@pytest.mark.asyncio
async def test_publish_event_no_subscriber_no_op() -> None:
    """没订阅者也不抛."""
    from app.schemas.generation import SseEvent
    await gen._publish_event(
        "a-no-sub",
        SseEvent(event="done", asset_id="a-no-sub", ts=_now()),
    )


# ─── _stage_collect (纯 await sleep, 不调 LLM) ─────────────────────


@pytest.mark.asyncio
async def test_stage_collect_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """_stage_collect (T131.2): 优先读 value_segments. 这个测试 mock value_segments
    返非空, 验证 metadata 含 candidates_count / trust_score_avg / events +
    collect_source='value_segments'."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    gen._assets["a1"] = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    fake_segments = [
        {
            "id": "seg-1", "content": "c1", "trust_score": 0.9,
            "extracted_at": "2026-05-24T00:00:00Z",
            "source": {"type": "event", "event_id": "e1", "contributors": []},
        },
        {
            "id": "seg-2", "content": "c2", "trust_score": 0.5,
            "extracted_at": "2026-05-23T00:00:00Z",
            "source": {"type": "event", "event_id": "e2", "contributors": []},
        },
    ]

    class _FakeDb:
        def list_value_segments(
            self, project_id: str, min_trust: float = 0.0,
            from_iso: str | None = None, limit: int = 100,
        ) -> list[dict]:
            assert project_id == "p1"
            return fake_segments

        def list_events(self, **kw):
            raise AssertionError("不应回退到 events (value_segments 非空)")

    monkeypatch.setattr(gen, "get_db", lambda: _FakeDb())
    req = GenerateAssetRequest(type="weekly_report", time_window="this_week")
    metadata = await gen._stage_collect("a1", req)
    assert metadata["candidates_count"] == 2
    assert metadata["time_window"] == "this_week"
    assert metadata["trust_score_avg"] == 0.7  # (0.9 + 0.5) / 2
    assert metadata["collect_source"] == "value_segments"
    # 排序后 trust 高的在前; seg-1 segments id 翻译进入 event dict 'id'
    assert metadata["events"][0]["id"] == "seg-1"
    assert metadata["events"][0]["source_ref"] == "e1"


@pytest.mark.asyncio
async def test_stage_collect_falls_back_to_events_when_segments_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T131.2 · value_segments 空 → 退化到 db.list_events (向后兼容)."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    gen._assets["a1"] = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    fallback_events = [
        {"id": "e1", "title": "ev1", "content": "c1", "trust_score": 0.8,
         "occurred_at": "2026-05-24T00:00:00Z"},
    ]
    events_called = {"n": 0}

    class _FakeDb:
        def list_value_segments(self, **kw):
            return []  # 触发 fallback

        def list_events(self, **kw):
            events_called["n"] += 1
            return fallback_events, len(fallback_events)

    monkeypatch.setattr(gen, "get_db", lambda: _FakeDb())
    req = GenerateAssetRequest(type="weekly_report", time_window="this_week")
    metadata = await gen._stage_collect("a1", req)
    assert events_called["n"] == 1
    assert metadata["collect_source"] == "events_fallback"
    assert metadata["candidates_count"] == 1
    assert metadata["events"][0]["id"] == "e1"


# ─── _run_stage 通用执行器 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_stage_success_marks_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_stage: 成功 → status=done + 推 stage_completed 事件."""
    gen._assets["a1"] = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._progress["a1"] = gen._initial_progress("a1")
    gen._chapters["a1"] = []

    async def fake_work() -> dict:
        return {"foo": "bar"}

    await gen._run_stage("a1", "collect", fake_work())
    p = gen._progress["a1"]
    collect_stage = next(s for s in p.stages if s.name == "collect")
    assert collect_stage.status == "done"
    assert collect_stage.metadata == {"foo": "bar"}


@pytest.mark.asyncio
async def test_run_stage_failure_marks_failed_and_raises() -> None:
    gen._assets["a1"] = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._progress["a1"] = gen._initial_progress("a1")
    gen._chapters["a1"] = []

    async def fail_work() -> dict:
        raise RuntimeError("LLM down")

    with pytest.raises(RuntimeError):
        await gen._run_stage("a1", "outline", fail_work())
    p = gen._progress["a1"]
    outline_stage = next(s for s in p.stages if s.name == "outline")
    assert outline_stage.status == "failed"
    assert outline_stage.error and "LLM down" in outline_stage.error
    assert p.overall_status == "failed"


# ─── start_generation + 完整 pipeline (mock LLM) ───────────────────


@pytest.mark.asyncio
async def test_start_generation_returns_asset_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start_generation 立即返回 status=generating 不等 pipeline."""
    monkeypatch.setattr(asyncio, "create_task", lambda coro: None)
    # 避免协程 warning
    monkeypatch.setattr(gen, "_run_pipeline", AsyncMock())
    req = GenerateAssetRequest(type="weekly_report", time_window="2026-W21")
    asset = await gen.start_generation("proj-1", req, user_id="u-1")
    assert asset.status == "generating"
    assert asset.id.startswith("asset-")
    assert asset.project_id == "proj-1"
    assert asset.created_by == "u-1"
    assert gen._assets[asset.id] is asset


# ─── regenerate_chapter · 失败路径 ─────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_chapter_missing_chapter_returns_none() -> None:
    gen._assets["a1"] = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._chapters["a1"] = []
    result = await gen.regenerate_chapter("a1", "ch-fake", "rewrite")
    assert result is None


@pytest.mark.asyncio
async def test_regenerate_chapter_missing_asset_returns_none() -> None:
    result = await gen.regenerate_chapter("a-fake", "ch-fake", "x")
    assert result is None


@pytest.mark.asyncio
async def test_regenerate_chapter_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mock router.generate → 章节内容更新 + history 追加."""
    gen._assets["a1"] = Asset(
        id="a1", project_id="p", type="weekly_report", title="t",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    original_chapter = Chapter(
        id="ch-1", asset_id="a1", order_index=0,
        title="§1", content="原始内容",
    )
    gen._chapters["a1"] = [original_chapter]

    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=_make_llm_response(
            text="这是新生成的章节内容, 足够长以通过 30 字符门槛检查. [1] 详情见 PR.",
        ),
    )

    async def get_fake_router():
        return fake_router

    monkeypatch.setattr(gen, "get_router", get_fake_router)

    result = await gen.regenerate_chapter(
        "a1", "ch-1", "更生动一些", user_id="u-1",
    )
    assert result is original_chapter
    assert "新生成的章节内容" in original_chapter.content
    assert len(original_chapter.regeneration_history) == 1
    assert original_chapter.regeneration_history[0]["instruction"] == "更生动一些"


# ─── _bootstrap_from_db 启动加载 ──────────────────────────────────


def test_bootstrap_from_db_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 SQLite 数据 → 安静返回, 不抛."""
    class FakeDb:
        def load_all_assets(self) -> list:
            return []

        def load_all_evidence(self) -> dict:
            return {}

        def load_chapters_for_asset(self, _id: str) -> list:
            return []

        def load_progress(self, _id: str) -> None:
            return None

        def load_all_redaction_jobs(self) -> dict:
            return {}

        def load_all_publish_records(self) -> list:
            return []

        def stats(self) -> dict:
            return {"assets": 0, "chapters": 0, "evidence": 0,
                    "publish_records": 0, "redaction_jobs": 0}

    monkeypatch.setattr(gen, "get_db", lambda: FakeDb())
    # 不抛
    gen._bootstrap_from_db()
