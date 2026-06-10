"""HTTP API · v0.5.1 站内通知 (T49 写入 + T51 前端读取).

端点 (MVP 单租户, user_id 通过 query param 传; 生产应换为 JWT session):
    GET  /me/notifications?user_id=&limit=&unread_only=  → list + count
    GET  /me/notifications/unread-count?user_id=         → {unread_count}
    POST /me/notifications/:id/read                       → mark read
    POST /me/notifications/read-all?user_id=             → mark all read

设计依据:
- T49 §6 数据模型 + T51 §6 API
- 与 skills consent endpoints 同 user_id-via-param 模式
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.config.logging import logger
from app.gateway.http_api._session import require_user_id
from app.persistence import store as store_module
from app.schemas.notification import (
    WebNotification,
    WebNotificationListResponse,
)
from app.services import notification_sse

router = APIRouter(prefix="/me/notifications", tags=["notifications"])

_SSE_HEARTBEAT_S = 15.0


def _enforce_self_or_400(session_user: str, target_user: str) -> None:
    """v1.0.1 安全修复: query 中的 user_id 必须等于 session, 否则 403.

    MVP backward-compat: 缺 X-User-Id 时 require_user_id 已经 401, 不会进入这里.
    """
    if session_user != target_user:
        raise HTTPException(
            403,
            detail=(
                f"user_id query param ({target_user}) "
                f"must match session ({session_user})"
            ),
        )


@router.get("", response_model=WebNotificationListResponse)
async def list_notifications(
    session_user: str = Depends(require_user_id),
    user_id: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
) -> WebNotificationListResponse:
    """列出当前用户的通知 (按 created_at DESC).

    v1.0.1: session_user 必须 == user_id (防订阅他人通知).
    """
    _enforce_self_or_400(session_user, user_id)
    db = store_module.get_db()
    raw_items = db.list_notifications_for_user(
        user_id=user_id, unread_only=unread_only, limit=limit
    )
    items = [WebNotification.model_validate(r) for r in raw_items]
    unread_count = db.count_unread_notifications(user_id)
    return WebNotificationListResponse(items=items, unread_count=unread_count)


@router.get("/unread-count")
async def unread_count(
    session_user: str = Depends(require_user_id),
    user_id: str = Query(..., min_length=1, max_length=128),
) -> dict[str, int]:
    """铃铛角标轮询用. v1.0.1: session_user 必须 == user_id."""
    _enforce_self_or_400(session_user, user_id)
    db = store_module.get_db()
    return {"unread_count": db.count_unread_notifications(user_id)}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    session_user: str = Depends(require_user_id),
) -> dict[str, bool]:
    """标记单条通知为已读. 不存在返 404.

    v1.0.1 安全修复: 校验 notification 归属当前 session_user, 否则 403.
    """
    db = store_module.get_db()
    raw = db.get_notification(notification_id)
    if raw is None:
        raise HTTPException(404, detail="Notification not found")
    if raw.get("user_id") != session_user:
        raise HTTPException(
            403,
            detail="Notification does not belong to current user",
        )
    db.mark_notification_read(notification_id)
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    session_user: str = Depends(require_user_id),
    user_id: str = Query(..., min_length=1, max_length=128),
) -> dict[str, int]:
    """标记当前用户所有未读为已读. v1.0.1: session_user 必须 == user_id."""
    _enforce_self_or_400(session_user, user_id)
    db = store_module.get_db()
    affected = db.mark_all_notifications_read(user_id)
    logger.info(
        "notifications_mark_all_read", user_id=user_id, affected=affected
    )
    return {"affected": affected}


@router.get("/stream")
async def stream_notifications(
    request: Request,
    session_user: str = Depends(require_user_id),
    user_id: str = Query(..., min_length=1, max_length=128),
) -> StreamingResponse:
    """SSE 推送当前用户的 consent 事件 (T52).

    事件: consent_request / consent_signed / consent_rejected / consent_expired / snapshot
    断开重连由前端 EventSource 自动处理.

    v1.0.1: session_user 必须 == user_id (防订阅他人 SSE).
    隐私: 严格按 user_id 路由, 不广播 project 内其他用户的事件.
    """
    _enforce_self_or_400(session_user, user_id)
    queue = await notification_sse.subscribe(user_id)
    db = store_module.get_db()

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            # 1. 发一次 snapshot (当前 unread_count) 让晚连客户端立刻同步
            try:
                unread = db.count_unread_notifications(user_id)
                snapshot = notification_sse.SseNotificationEvent(
                    event="snapshot",
                    user_id=user_id,
                    unread_count=unread,
                )
                yield _sse_format(
                    event="snapshot", data=snapshot.to_json()
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "notification_sse_snapshot_failed",
                    user_id=user_id, error=str(e),
                )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(
                        queue.get(), timeout=_SSE_HEARTBEAT_S
                    )
                except TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                yield _sse_format(event=ev.event, data=ev.to_json())
        finally:
            await notification_sse.cleanup(user_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关 nginx buffering
            "Connection": "keep-alive",
        },
    )


def _sse_format(*, event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode()
