"""IM 蒸馏异步 job 管理 (v0.3.1 H).

设计:
- POST /distill 立刻返 {job_id, status: "pending"}; 后台 task 跑实际蒸馏
- GET /distill-jobs/{job_id}/stream → SSE 推送进度
  · 事件: started / progress / completed / failed
- 内存 job dict, 不持久化 (重启丢; v0.4 加 SQLite job 表)

流程:
    POST /distill
        → create_job(...) → 后台 task → 推 SSE → 完成
    GET /distill-jobs/{id}/stream
        → 取 job.sse_queue → 持续 yield events
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.config.logging import logger
from app.schemas.im import IMSourceMode


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DistillJob:
    """单次蒸馏 job 状态."""

    job_id: str
    connection_id: str
    project_id: str
    chat_id: str
    source_mode: IMSourceMode
    status: JobStatus = JobStatus.PENDING
    messages_total: int = 0
    messages_processed: int = 0
    segments_persisted: int = 0
    segment_ids: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class _JobRegistry:
    """单进程内存 job 池. MVP 不持久化."""

    def __init__(self) -> None:
        self._jobs: dict[str, DistillJob] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.RLock()

    def create(
        self,
        connection_id: str,
        project_id: str,
        chat_id: str,
        source_mode: IMSourceMode,
    ) -> DistillJob:
        job_id = f"distill-{uuid.uuid4().hex[:12]}"
        with self._lock:
            job = DistillJob(
                job_id=job_id,
                connection_id=connection_id,
                project_id=project_id,
                chat_id=chat_id,
                source_mode=source_mode,
            )
            self._jobs[job_id] = job
            self._queues[job_id] = []
        return job

    def get(self, job_id: str) -> DistillJob | None:
        return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        **changes,
    ) -> DistillJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for k, v in changes.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            job.updated_at = datetime.now(timezone.utc)
            return job

    def publish_event(self, job_id: str, event: dict[str, Any]) -> None:
        """非阻塞推到所有订阅 queue."""
        for q in list(self._queues.get(job_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("distill_sse_queue_full", job_id=job_id)

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._queues.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            queues = self._queues.get(job_id, [])
            if q in queues:
                queues.remove(q)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._queues.clear()


_registry = _JobRegistry()


def get_registry() -> _JobRegistry:
    return _registry


# ─── 后台执行 ────────────────────────────────────────────────


async def run_distill_job(job_id: str) -> None:
    """后台 task: 实际跑蒸馏并推 SSE."""
    from datetime import datetime as _dt
    from app.persistence import get_db
    from app.schemas.im import IMUser
    from app.services.im.connector_base import IMNormalizedMessage
    from app.services.im.value_segment_service import (
        assemble_segments,
        persist_segments,
    )
    from app.services.im.signal_gate import classify_batch_async

    job = _registry.get(job_id)
    if job is None:
        return
    _registry.update(job_id, status=JobStatus.RUNNING)
    _registry.publish_event(job_id, {"event": "started", "job_id": job_id})

    try:
        db = get_db()
        rows = db.list_im_messages(job.connection_id, chat_id=job.chat_id, limit=2000)
        _registry.update(job_id, messages_total=len(rows))
        if not rows:
            _registry.update(
                job_id,
                status=JobStatus.COMPLETED,
                segments_persisted=0,
                segment_ids=[],
            )
            _registry.publish_event(job_id, {
                "event": "completed",
                "segments_persisted": 0,
                "segment_ids": [],
            })
            return

        # 转 IMNormalizedMessage
        msgs: list[IMNormalizedMessage] = []
        for r in rows:
            sender_data = r.get("sender") or {}
            sender = IMUser(
                user_id=sender_data.get("user_id", ""),
                name=sender_data.get("name"),
            )
            msgs.append(IMNormalizedMessage(
                platform="feishu",
                platform_chat_id=r["platform_chat_id"],
                platform_msg_id=r["platform_msg_id"],
                sender=sender,
                content=r.get("content") or "",
                mentions=r.get("mentions") or [],
                received_at=_dt.fromisoformat(r["received_at"]),
                raw_event_type="message",
            ))
        msgs.sort(key=lambda m: m.received_at)

        _registry.publish_event(job_id, {
            "event": "progress", "stage": "classifying",
            "total": len(msgs),
        })
        # 跑异步 SignalGate (R10 走 Qwen 兜底)
        signals = await classify_batch_async(msgs, use_llm=True)
        _registry.update(job_id, messages_processed=len(msgs))
        _registry.publish_event(job_id, {
            "event": "progress", "stage": "assembling",
            "signals_found": sum(1 for s in signals if s.is_signal),
        })

        segments = assemble_segments(msgs, signals)
        persisted = persist_segments(
            job.project_id, segments, source_mode=job.source_mode
        )
        seg_ids = [s.id for s in persisted]

        _registry.update(
            job_id,
            status=JobStatus.COMPLETED,
            segments_persisted=len(persisted),
            segment_ids=seg_ids,
        )
        _registry.publish_event(job_id, {
            "event": "completed",
            "segments_persisted": len(persisted),
            "segment_ids": seg_ids,
        })
        logger.info(
            "distill_job_completed",
            job_id=job_id,
            messages=len(msgs),
            segments=len(persisted),
        )
    except Exception as e:
        _registry.update(job_id, status=JobStatus.FAILED, error=str(e))
        _registry.publish_event(job_id, {
            "event": "failed",
            "error": str(e),
        })
        logger.error("distill_job_failed", job_id=job_id, error=str(e))


def start_distill_job(
    project_id: str,
    connection_id: str,
    chat_id: str,
    source_mode: IMSourceMode = "assistant",
) -> DistillJob:
    """同步创建 job + asyncio.create_task 启后台. 立刻返."""
    job = _registry.create(connection_id, project_id, chat_id, source_mode)
    asyncio.create_task(run_distill_job(job.job_id), name=f"distill-{job.job_id}")
    return job
