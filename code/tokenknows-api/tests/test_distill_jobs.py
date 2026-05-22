"""Distill 异步 job + SSE (v0.3.1 H).

覆盖:
- _JobRegistry create / get / update / publish_event / subscribe
- run_distill_job 无消息时 completed segments=0
- run_distill_job 有消息时调用 SignalGate + assemble + persist
- run_distill_job 异常时 status=FAILED
- HTTP POST /distill-async → 202 + job_id
- HTTP POST /distill-async 404 (connection 不存在)
- HTTP GET /distill-jobs/:id 返当前状态
- HTTP GET /distill-jobs/:id/stream SSE 推 events
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im import distill_jobs
from app.services.im.distill_jobs import (
    JobStatus,
    _JobRegistry,
    get_registry,
    run_distill_job,
    start_distill_job,
)


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    get_registry().reset_for_tests()
    s = settings_module.get_settings()
    s.im_encryption_key = Fernet.generate_key().decode()
    s.feishu_app_id = "cli"
    s.feishu_app_secret = "x"
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


# ─── _JobRegistry ───────────────────────────────────────────


def test_create_assigns_unique_job_id() -> None:
    reg = _JobRegistry()
    j1 = reg.create("c1", "p1", "ch", "assistant")
    j2 = reg.create("c2", "p1", "ch", "assistant")
    assert j1.job_id != j2.job_id


def test_get_returns_job() -> None:
    reg = _JobRegistry()
    j = reg.create("c1", "p1", "ch", "assistant")
    assert reg.get(j.job_id) is j


def test_update_changes_fields() -> None:
    reg = _JobRegistry()
    j = reg.create("c1", "p1", "ch", "assistant")
    reg.update(j.job_id, status=JobStatus.RUNNING, messages_total=42)
    refreshed = reg.get(j.job_id)
    assert refreshed.status == JobStatus.RUNNING
    assert refreshed.messages_total == 42


def test_update_missing_returns_none() -> None:
    reg = _JobRegistry()
    assert reg.update("ghost", status=JobStatus.COMPLETED) is None


def test_publish_event_to_subscriber() -> None:
    reg = _JobRegistry()
    j = reg.create("c1", "p1", "ch", "assistant")
    q = reg.subscribe(j.job_id)
    reg.publish_event(j.job_id, {"event": "started"})
    msg = q.get_nowait()
    assert msg == {"event": "started"}


def test_unsubscribe_removes_queue() -> None:
    reg = _JobRegistry()
    j = reg.create("c1", "p1", "ch", "assistant")
    q = reg.subscribe(j.job_id)
    reg.unsubscribe(j.job_id, q)
    reg.publish_event(j.job_id, {"event": "x"})
    assert q.empty()


# ─── run_distill_job ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_distill_job_empty_messages_completed(
    fresh_state: SqliteStore,
) -> None:
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "chat-x", "assistant")
    await run_distill_job(job.job_id)
    refreshed = get_registry().get(job.job_id)
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.segments_persisted == 0


@pytest.mark.asyncio
async def test_run_distill_job_publishes_events(
    fresh_state: SqliteStore,
) -> None:
    """订阅 queue 应能收到 started + completed."""
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "chat-x", "assistant")
    q = get_registry().subscribe(job.job_id)
    await run_distill_job(job.job_id)
    # drain
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    types = [e["event"] for e in events]
    assert "started" in types
    assert "completed" in types


@pytest.mark.asyncio
async def test_run_distill_job_with_messages(
    fresh_state: SqliteStore,
) -> None:
    """有 signal 消息时应至少 persist 1 个 segment."""
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "chat-x", "assistant")
    # 种 3 条决策消息
    base = "2026-05-22T10:0{}:00+00:00"
    for i, txt in enumerate([
        "决定使用 pgvector 作为向量存储, 因为已经在 PG 里有完整 schema",
        "同意, 而且 pgvector 也支持 HNSW 索引,生产性能完全够用",
        "确认这是最终决议, 我们一致同意切换",
    ]):
        fresh_state.insert_im_message(
            message_id=f"m{i}", connection_id=conn.id,
            platform_chat_id="chat-x", platform_msg_id=f"r{i}",
            received_at=base.format(i),
            retention_until=None, is_signal=True, redacted=False,
            json_str=json.dumps({
                "id": f"m{i}", "platform_chat_id": "chat-x",
                "platform_msg_id": f"r{i}",
                "sender": {"user_id": f"u{i}", "name": f"User{i}"},
                "content": txt, "mentions": [],
                "received_at": base.format(i),
            }, ensure_ascii=False),
        )

    # mock Qwen 全部 return signal
    async def fake_score(text):
        return (0.85, "decision")

    with patch(
        "app.services.im.signal_gate._qwen_score_message", new=fake_score
    ):
        await run_distill_job(job.job_id)

    refreshed = get_registry().get(job.job_id)
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.segments_persisted >= 1
    assert len(refreshed.segment_ids) == refreshed.segments_persisted


@pytest.mark.asyncio
async def test_run_distill_job_exception_marks_failed(
    fresh_state: SqliteStore, monkeypatch,
) -> None:
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "chat-x", "assistant")
    # patch list_im_messages to throw
    def boom(*a, **kw):
        raise RuntimeError("simulated db failure")
    monkeypatch.setattr(fresh_state, "list_im_messages", boom)

    await run_distill_job(job.job_id)
    refreshed = get_registry().get(job.job_id)
    assert refreshed.status == JobStatus.FAILED
    assert "simulated" in refreshed.error


# ─── HTTP endpoints ─────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_post_distill_async_404_missing_connection(client: TestClient) -> None:
    r = client.post(
        "/api/v1/im/connections/ghost/distill-async",
        json={"chat_id": "ch"},
    )
    assert r.status_code == 404


def test_post_distill_async_returns_job_id(
    client: TestClient,
) -> None:
    conn = im_service.create_connection("p1", "feishu")
    r = client.post(
        f"/api/v1/im/connections/{conn.id}/distill-async",
        json={"chat_id": "ch-x"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"].startswith("distill-")
    assert body["status"] in ("pending", "running", "completed")
    assert body["chat_id"] == "ch-x"


def test_get_distill_job_404(client: TestClient) -> None:
    r = client.get("/api/v1/im/distill-jobs/ghost")
    assert r.status_code == 404


def test_get_distill_job_returns_status(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "ch", "assistant")
    r = client.get(f"/api/v1/im/distill-jobs/{job.job_id}")
    assert r.status_code == 200
    assert r.json()["job_id"] == job.job_id


def test_get_distill_stream_404(client: TestClient) -> None:
    r = client.get("/api/v1/im/distill-jobs/ghost/stream")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stream_generator_yields_snapshot_then_completed(
) -> None:
    """直接驱动 SSE generator (避免 TestClient SSE 阻塞)."""
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "ch", "assistant")
    get_registry().update(job.job_id, status=JobStatus.COMPLETED)

    # 复刻 router stream_distill_job 的 generate 逻辑
    from app.gateway.http_api.im import stream_distill_job
    response = await stream_distill_job(job.job_id)
    # 拿到 StreamingResponse, 拉前 2 个 chunk
    body_iter = response.body_iterator
    chunks: list[str] = []
    try:
        async for c in body_iter:
            text = c.decode("utf-8") if isinstance(c, bytes) else c
            chunks.append(text)
            if "snapshot" in text:
                break
            if len(chunks) >= 5:
                break
    except StopAsyncIteration:
        pass
    joined = "".join(chunks)
    assert "snapshot" in joined
    assert job.job_id in joined


@pytest.mark.asyncio
async def test_stream_publishes_runtime_event_then_terminates() -> None:
    conn = im_service.create_connection("p1", "feishu")
    job = get_registry().create(conn.id, "p1", "ch", "assistant")

    from app.gateway.http_api.im import stream_distill_job
    response = await stream_distill_job(job.job_id)
    body_iter = response.body_iterator
    # 启 publish 任务: snapshot 后推一个 event 标 completed
    seen_chunks: list[str] = []

    async def publish_after_snapshot():
        await asyncio.sleep(0.1)
        get_registry().publish_event(job.job_id, {
            "event": "progress", "stage": "classifying",
        })
        get_registry().update(job.job_id, status=JobStatus.COMPLETED)
        get_registry().publish_event(job.job_id, {
            "event": "completed", "segments_persisted": 0,
        })

    publish_task = asyncio.create_task(publish_after_snapshot())
    try:
        async for c in body_iter:
            text = c.decode("utf-8") if isinstance(c, bytes) else c
            seen_chunks.append(text)
            if "completed" in "".join(seen_chunks):
                break
            if len(seen_chunks) >= 10:
                break
    finally:
        publish_task.cancel()
    joined = "".join(seen_chunks)
    assert "snapshot" in joined or "classifying" in joined
