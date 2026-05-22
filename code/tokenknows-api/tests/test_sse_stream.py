"""SSE stream endpoint internals · 直接测 event_stream generator.

通过 httpx ASGI 测试客户端读 SSE chunks (有限循环).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from app.schemas.asset import Asset
from app.schemas.generation import SseEvent
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_p = dict(gen._progress)
    snap_q = dict(gen._sse_queues)
    gen._assets.clear()
    gen._chapters.clear()
    gen._progress.clear()
    gen._sse_queues.clear()
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._progress.clear()
    gen._sse_queues.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._progress.update(snap_p)
    gen._sse_queues.update(snap_q)


def _seed_asset(asset_id: str = "asset-sse-1") -> None:
    a = Asset(
        id=asset_id, project_id="p1", type="weekly_report",
        title="t", status="generating", current_version=0, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    gen._assets[asset_id] = a
    gen._chapters[asset_id] = []
    gen._progress[asset_id] = gen._initial_progress(asset_id)


# ─── SSE generator 直接调用 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_stream_emits_snapshot_then_done() -> None:
    """流式: 收到 snapshot + 1 个 done event → break."""
    _seed_asset("a1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 启动 SSE 流后异步推一个 done 事件
        async def push_done():
            await asyncio.sleep(0.1)   # 等订阅注册
            await gen._publish_event(
                "a1",
                SseEvent(event="done", asset_id="a1", ts=_now(),
                         payload={"chapters_total": 5}),
            )

        push_task = asyncio.create_task(push_done())

        async with client.stream("GET", "/api/v1/assets/a1/generation/stream") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            chunks_text = ""
            async for chunk in r.aiter_text():
                chunks_text += chunk
                if "done" in chunks_text:
                    break
                if len(chunks_text) > 5000:   # safety cap
                    break

        await push_task

    assert "event: snapshot" in chunks_text
    assert "event: done" in chunks_text


@pytest.mark.asyncio
async def test_sse_stream_404_for_missing_progress() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/assets/asset-no-progress/generation/stream")
        assert r.status_code == 404
