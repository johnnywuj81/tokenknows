"""站内通知 (v0.5.1 T49).

ConsentNotifier 写入的 web 兜底通知; 也用于 sign/reject 后回执到原通知者.

types:
- consent_request   ← 蒸馏出 skill 待 contributor 同意
- consent_signed    ← 某 contributor 签了 (回执给其他 contributor / project owner)
- consent_rejected  ← 某 contributor 拒了
- consent_expired   ← 30 天超时自动 expire

SSE 事件名: auto_trigger.consent_request 等; 按 user_id 路由 (隐私).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NotificationType = Literal[
    "consent_request",
    "consent_signed",
    "consent_rejected",
    "consent_expired",
]


class WebNotification(BaseModel):
    """站内通知 (持久化到 notifications 表)."""

    id: str
    """notification-{uuid} 12 hex."""

    user_id: str
    """接收者 platform user_id (open_id / userid / ...)."""

    type: NotificationType

    title: str
    """≤ 80 字 (UI 铃铛 popover 单行)."""

    body: str
    """≤ 400 字 (popover 摘要)."""

    link_url: str
    """点击跳转 (e.g. /skills/skill-xxx?action=sign).
    PUBLIC_BASE_URL 未配时也允许相对路径."""

    read: bool = False
    """已读标记 (mark_read endpoint 改)."""

    created_at: datetime

    related_skill_id: str | None = None
    """关联的 skill (consent_* 类型必填)."""


# ─── 请求 / 响应 DTO ──────────────────────────────────────────────


class WebNotificationListResponse(BaseModel):
    """GET /api/v1/notifications response."""

    items: list[WebNotification] = Field(default_factory=list)
    unread_count: int = 0
