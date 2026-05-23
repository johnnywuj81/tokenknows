"""Skill Review 通知器 · v0.6.0 T57.

3 类通知:
- skill_review_request: submit_for_review 后给 reviewer
- skill_review_approved: approve 后给作者
- skill_review_rejected: reject 后给作者 + reason

Reviewer 路由策略 (MVP):
- endpoint body 传 reviewer_id 时优先 (作者主动指定)
- 否则: 项目下所有 contributors 都收 (任何 contributor 都可以是 reviewer)
- 生产应换为 project_owner / 显式 reviewer role

数据流:
  endpoint POST /submit-for-review (body 含 user_id, 可选 reviewer_user_ids)
    ↓ submit_for_review(skill, user_id)
    ↓ upsert_skill
    ↓ notify_review_request(skill, reviewers=[r1, r2])
      ↓ web notification + SSE event 推给每个 reviewer
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from app.config.logging import logger
from app.config.settings import get_settings
from app.persistence import store as store_module
from app.schemas.notification import NotificationType, WebNotification
from app.schemas.skill import Skill


_ReviewKind = Literal[
    "skill_review_request",
    "skill_review_approved",
    "skill_review_rejected",
]


def notify_review_request(
    skill: Skill,
    *,
    reviewer_user_ids: list[str],
    author_user_id: str,
) -> int:
    """submit_for_review 后给 reviewer 发通知 (web + SSE).

    Returns: 实际写入条数.
    """
    if not reviewer_user_ids:
        return 0
    title = f"📝 待审批: Skill《{skill.name}》"
    body = (
        f"作者 {author_user_id} 提交了 Skill 草稿请你审批; "
        f"建议在 7 天内决定."
    )
    return _notify_each(
        skill,
        type_="skill_review_request",
        recipient_user_ids=reviewer_user_ids,
        title=title,
        body=body,
        extra={"author_user_id": author_user_id},
    )


def notify_review_decision(
    skill: Skill,
    *,
    type_: _ReviewKind,
    author_user_id: str,
    reviewer_id: str,
    reason: str | None = None,
) -> int:
    """approve / reject 后给作者发通知."""
    if type_ == "skill_review_request":
        raise ValueError("review request 用 notify_review_request")
    if type_ == "skill_review_approved":
        title = f"✅ Skill《{skill.name}》已批准发布"
        body = f"Reviewer {reviewer_id} 批准了你的 skill, 已自动转 active 状态."
    elif type_ == "skill_review_rejected":
        title = f"❌ Skill《{skill.name}》被退回"
        body = (
            f"Reviewer {reviewer_id} 退回了你的 skill; "
            f"原因: {reason or '(未提供)'}. 修订后可重新提交."
        )
    else:
        raise ValueError(f"unknown review notification type: {type_}")

    return _notify_each(
        skill,
        type_=type_,
        recipient_user_ids=[author_user_id],
        title=title,
        body=body,
        extra={"reviewer_id": reviewer_id, "reason": reason},
    )


# ─── 内部 helper ──────────────────────────────────────────


def _notify_each(
    skill: Skill,
    *,
    type_: NotificationType,
    recipient_user_ids: list[str],
    title: str,
    body: str,
    extra: dict | None = None,
) -> int:
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"
    now = datetime.now(timezone.utc)
    db = store_module.get_db()

    count = 0
    for uid in recipient_user_ids:
        notif = WebNotification(
            id=f"notif-{uuid.uuid4().hex[:12]}",
            user_id=uid,
            type=type_,
            title=title,
            body=body,
            link_url=link,
            read=False,
            created_at=now,
            related_skill_id=skill.id,
        )
        try:
            db.upsert_notification(
                notification_id=notif.id,
                user_id=notif.user_id,
                type_=notif.type,
                related_skill_id=notif.related_skill_id,
                read=notif.read,
                created_at=notif.created_at.isoformat(),
                json_str=notif.model_dump_json(),
            )
            _publish_sse(notif, skill_id=skill.id, extra=extra)
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "review_notify_failed",
                skill_id=skill.id,
                user_id=uid,
                notif_type=type_,
                error=str(e),
            )
    return count


def _publish_sse(
    notif: WebNotification,
    *,
    skill_id: str,
    extra: dict | None = None,
) -> None:
    try:
        from app.services import notification_sse
        from app.services.notification_sse import SseNotificationEvent

        db = store_module.get_db()
        unread = db.count_unread_notifications(notif.user_id)
        ev = SseNotificationEvent(
            event=notif.type,  # type: ignore[arg-type]
            user_id=notif.user_id,
            skill_id=skill_id,
            notification_id=notif.id,
            unread_count=unread,
            extra=extra,
        )
        notification_sse.publish_to_user(notif.user_id, ev)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "review_sse_publish_failed",
            user_id=notif.user_id,
            error=str(e),
        )


__all__ = ["notify_review_decision", "notify_review_request"]
