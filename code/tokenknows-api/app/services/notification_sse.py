"""User-scoped SSE pub/sub for v0.5.2 notifications (T52).

与 generation_service._sse_queues 类似, 但 key 是 user_id 而非 asset_id;
ConsentNotifier / sign / reject / sweep 写入 web notification 后立刻调
`publish_to_user(user_id, event)`, 前端 EventSource 实时收到.

设计原则:
- 单进程内存 fan-out (MVP 单实例); 多实例需换 Redis pub/sub
- 每用户多 queue (多 tab / 多设备同时打开)
- 队列满 → 丢弃单事件 + log warning (容忍单客户端慢)
- 客户端断开由 endpoint 层调 cleanup_sse 显式回收

事件类型 (与 NotificationType 对齐 + ack 控制事件):
- consent_request / consent_signed / consent_rejected / consent_expired
- snapshot (订阅时一次性发当前 unread_count)
- heartbeat (15s 防 proxy 掐线)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.config.logging import logger


# user_id → list[Queue]; 多 tab 都收
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_state_lock = asyncio.Lock()

# 单 queue 容量; 慢客户端短时间收 64 条后开始丢
_QUEUE_MAXSIZE = 64


SseNotificationEventType = Literal[
    "consent_request",
    "consent_signed",
    "consent_rejected",
    "consent_expired",
    "snapshot",
]


@dataclass
class SseNotificationEvent:
    """user-scoped SSE 事件 payload."""

    event: SseNotificationEventType
    user_id: str
    """目标用户 (用于断言路由正确)."""
    skill_id: str | None = None
    notification_id: str | None = None
    unread_count: int | None = None
    """snapshot / 关键 mark_read 时一同推, 省一次 HTTP."""
    extra: dict[str, Any] | None = None
    """额外字段 (sign 的 signed_count/required_count 等)."""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        return json.dumps(
            {
                "event": self.event,
                "user_id": self.user_id,
                "skill_id": self.skill_id,
                "notification_id": self.notification_id,
                "unread_count": self.unread_count,
                "extra": self.extra or {},
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
        )


async def subscribe(user_id: str) -> asyncio.Queue:
    """订阅 user_id 的 SSE 事件; 返回 queue, cleanup 由调用方负责."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    async with _state_lock:
        _sse_queues.setdefault(user_id, []).append(queue)
    logger.debug(
        "notification_sse_subscribed",
        user_id=user_id,
        active_queues=len(_sse_queues[user_id]),
    )
    return queue


async def cleanup(user_id: str, queue: asyncio.Queue) -> None:
    """endpoint 断开时清理 queue. 用户最后一个 queue 移除后整个 entry 删."""
    async with _state_lock:
        queues = _sse_queues.get(user_id, [])
        _sse_queues[user_id] = [q for q in queues if q is not queue]
        if not _sse_queues[user_id]:
            _sse_queues.pop(user_id, None)
    logger.debug("notification_sse_cleanup", user_id=user_id)


def publish_to_user(user_id: str, event: SseNotificationEvent) -> int:
    """同步入口 (无 await, 给 sync 调用方如 consent_notifier 用).

    内部用 queue.put_nowait; 满 → 丢 + warn.
    Returns: 投递成功的 queue 数 (0 = 该用户无活跃订阅).

    注意: 调用方应确认 event.user_id == user_id (调用者保证路由正确).
    """
    if event.user_id != user_id:
        logger.warning(
            "notification_sse_user_mismatch",
            event_user=event.user_id,
            target_user=user_id,
        )
        return 0
    queues = _sse_queues.get(user_id, [])
    delivered = 0
    for q in queues:
        try:
            q.put_nowait(event)
            delivered += 1
        except asyncio.QueueFull:
            logger.warning(
                "notification_sse_queue_full",
                user_id=user_id,
                event_type=event.event,
            )
    return delivered


async def publish_to_user_async(
    user_id: str, event: SseNotificationEvent
) -> int:
    """async 入口 (sign/reject endpoint async 上下文用)."""
    return publish_to_user(user_id, event)


def active_user_count() -> int:
    """监控: 当前订阅 SSE 的活跃 user 数."""
    return len(_sse_queues)


def queues_for_user(user_id: str) -> int:
    """测试 helper: 某 user 的活跃 queue 数."""
    return len(_sse_queues.get(user_id, []))


def reset_for_tests() -> None:
    """测试 cleanup: 清空所有订阅."""
    _sse_queues.clear()


__all__ = [
    "SseNotificationEvent",
    "SseNotificationEventType",
    "active_user_count",
    "cleanup",
    "publish_to_user",
    "publish_to_user_async",
    "queues_for_user",
    "reset_for_tests",
    "subscribe",
]
