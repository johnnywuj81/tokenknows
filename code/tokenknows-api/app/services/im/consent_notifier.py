"""ConsentNotifier · v0.5.1 T49.

Skill 进入 pending_contributor_consent 时, 对每位 contributor 发:
  1. IM DM (主渠道, 飞书 interactive card / 钉/企微 stub)
  2. WebNotification (兜底, 即使 DM 失败也能在站内铃铛看见)

设计:
- sync 接口 (与 dispatch hook 同步路径自然衔接)
- 全异常 catch + log warning, 不阻塞主流程 (asset 已生成不能回滚)
- 同 skill 对同 contributor 去重 (避免重复 schedule 再次蒸馏)
- 飞书完整 (httpx.Client sync); 钉钉/企微 v0.5.0.x stub

Public API:
- notify_all(skill, im_connection_raw) -> NotifyReport
- notify_consent_signed/rejected/expired (回执给其他 contributor + project_owner)

数据流:
  initialize_pending(skill) 返回新 skill
    ↓ (调用方 upsert_skill 落盘)
  notify_all(skill, conn) -> 对每位 contributor 并发:
    _send_dm + _write_web_notification
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.config.logging import logger
from app.config.settings import get_settings
from app.persistence import store as store_module
from app.schemas.notification import NotificationType, WebNotification
from app.schemas.skill import Skill
from app.services.im_crypto import TokenCryptoError, decrypt_token


_HTTP_TIMEOUT = 10.0


# ─── Report 结构 ───────────────────────────────────────────


@dataclass
class _PerUserResult:
    user_id: str
    dm_ok: bool = False
    web_ok: bool = False
    skipped_dup: bool = False
    error: str | None = None


@dataclass
class NotifyReport:
    """notify_all 的汇总结果 (用于调试 + endpoint 回执)."""

    skill_id: str
    total: int = 0
    dm_success: int = 0
    web_success: int = 0
    skipped: int = 0
    per_user: list[_PerUserResult] = field(default_factory=list)


# ─── 主入口 notify_all ────────────────────────────────────


def notify_all(
    skill: Skill,
    *,
    connection_raw: dict | None,
) -> NotifyReport:
    """对每位 contributor 发 DM + web notification.

    Args:
        skill: 已经 initialize_pending 的 Skill (status=pending_contributor_consent)
        connection_raw: im_connections 表的 json (用于 DM API);
                        None / 缺 token 时跳过 DM, 只走 web 兜底

    Returns:
        NotifyReport 汇总每位 contributor 的成功情况.
        即使全 DM 失败, web notification 也应成功 (除非 DB 故障).
    """
    report = NotifyReport(skill_id=skill.id)
    if skill.status != "pending_contributor_consent":
        logger.warning(
            "consent_notify_wrong_status",
            skill_id=skill.id,
            status=skill.status,
        )
        return report
    if not skill.consent_required_from:
        return report  # 无需通知

    platform = (connection_raw or {}).get("platform", "")
    db = store_module.get_db()

    for user_id in skill.consent_required_from:
        result = _PerUserResult(user_id=user_id)

        # 去重: 同 skill + 同 user + type=consent_request 已存在则跳过
        existing = db.list_notifications_for_skill(skill.id, "consent_request")
        if any(n.get("user_id") == user_id for n in existing):
            result.skipped_dup = True
            report.skipped += 1
            report.per_user.append(result)
            continue

        # 1. web notification (兜底, 一定写)
        try:
            _write_web_notification(skill, user_id)
            result.web_ok = True
            report.web_success += 1
        except Exception as e:  # noqa: BLE001
            result.error = f"web_failed: {e}"
            logger.warning(
                "consent_web_notify_failed",
                skill_id=skill.id,
                user_id=user_id,
                error=str(e),
            )

        # 2. IM DM (best-effort)
        if connection_raw:
            try:
                ok = _send_dm(platform, connection_raw, skill, user_id)
                result.dm_ok = ok
                if ok:
                    report.dm_success += 1
            except Exception as e:  # noqa: BLE001
                result.error = (result.error or "") + f"; dm_failed: {e}"
                logger.warning(
                    "consent_dm_failed",
                    skill_id=skill.id,
                    user_id=user_id,
                    platform=platform,
                    error=str(e),
                )

        report.per_user.append(result)
        report.total += 1

    logger.info(
        "consent_notify_done",
        skill_id=skill.id,
        total=report.total,
        dm=report.dm_success,
        web=report.web_success,
        skipped=report.skipped,
    )
    return report


# ─── Web Notification ─────────────────────────────────────


def _write_web_notification(skill: Skill, user_id: str) -> WebNotification:
    """单条 web 通知 (consent_request 类型)."""
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"

    notif = WebNotification(
        id=f"notif-{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        type="consent_request",
        title="🤖 你的 Skill 草稿等待确认",
        body=(
            f"基于你最近的研发讨论, 我们自动蒸馏出了 Skill 草稿 "
            f"《{skill.name}》, 请确认是否发布."
        ),
        link_url=link,
        read=False,
        created_at=datetime.now(timezone.utc),
        related_skill_id=skill.id,
    )
    _persist_notification(notif)
    return notif


def _persist_notification(notif: WebNotification) -> None:
    db = store_module.get_db()
    db.upsert_notification(
        notification_id=notif.id,
        user_id=notif.user_id,
        type_=notif.type,
        related_skill_id=notif.related_skill_id,
        read=notif.read,
        created_at=notif.created_at.isoformat(),
        json_str=notif.model_dump_json(),
    )


# ─── IM DM 路由 ────────────────────────────────────────────


def _send_dm(
    platform: str,
    connection_raw: dict,
    skill: Skill,
    user_id: str,
) -> bool:
    """根据 platform 路由 DM 实现; 返回 True 表 DM 投递成功."""
    if platform == "feishu":
        return _send_dm_feishu(connection_raw, skill, user_id)
    if platform == "dingtalk":
        return _send_dm_dingtalk_stub(connection_raw, skill, user_id)
    if platform == "wework":
        return _send_dm_wework_stub(connection_raw, skill, user_id)
    logger.warning("consent_dm_unknown_platform", platform=platform)
    return False


# ─── 飞书 interactive card ────────────────────────────────


def _send_dm_feishu(
    connection_raw: dict, skill: Skill, user_id: str
) -> bool:
    """POST /open-apis/im/v1/messages?receive_id_type=open_id with interactive card."""
    auth_enc = connection_raw.get("auth_token_enc")
    if not auth_enc:
        logger.warning("consent_dm_feishu_no_token", skill_id=skill.id)
        return False
    try:
        access_token = decrypt_token(auth_enc)
    except TokenCryptoError as e:
        logger.warning(
            "consent_dm_feishu_decrypt_failed",
            skill_id=skill.id,
            error=str(e),
        )
        return False

    settings = get_settings()
    url = (
        f"{settings.feishu_api_base.rstrip('/')}"
        f"/open-apis/im/v1/messages?receive_id_type=open_id"
    )
    card = build_feishu_card(skill)
    body = {
        "receive_id": user_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(url, json=body, headers=headers)
    if resp.status_code != 200:
        logger.warning(
            "consent_dm_feishu_http_error",
            status=resp.status_code,
            body=resp.text[:200],
        )
        return False
    data = resp.json()
    if data.get("code") not in (0, None):
        logger.warning(
            "consent_dm_feishu_api_error",
            code=data.get("code"),
            msg=data.get("msg"),
        )
        return False
    logger.info(
        "consent_dm_feishu_ok",
        skill_id=skill.id,
        user_id=user_id,
        new_msg_id=(data.get("data") or {}).get("message_id"),
    )
    return True


def build_feishu_card(skill: Skill) -> dict[str, Any]:
    """构造飞书 interactive card 内容 (T49 §5 模板).

    public_base_url 未配时 button 用相对路径 (飞书客户端会按本机域名打开).
    """
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    detail_url = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"
    sign_url = f"{detail_url}?action=sign"
    reject_url = f"{detail_url}?action=reject"

    contributor_n = len(skill.contributors)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "🤖 你的 Skill 草稿等待确认",
            },
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{skill.name}**\n\n"
                        f"基于最近研发讨论 (含 {contributor_n} 位贡献者), "
                        f"我们自动蒸馏出了一份 Skill 草稿. \n"
                        f"请确认是否同意发布到项目知识库."
                    ),
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 同意发布"},
                        "type": "primary",
                        "url": sign_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                        "type": "danger",
                        "url": reject_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔍 查看详情"},
                        "url": detail_url,
                    },
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "30 天内未响应将自动归档为 expired_no_consent.",
                    }
                ],
            },
        ],
    }


# ─── 钉钉 / 企微 stub ──────────────────────────────────────


def _send_dm_dingtalk_stub(
    connection_raw: dict, skill: Skill, user_id: str
) -> bool:
    logger.info(
        "consent_dm_dingtalk_stub",
        skill_id=skill.id,
        user_id=user_id,
        note="v0.5.1.1 will call robot/send user-level with ActionCard",
    )
    return False  # stub 不算 dm_success


def _send_dm_wework_stub(
    connection_raw: dict, skill: Skill, user_id: str
) -> bool:
    logger.info(
        "consent_dm_wework_stub",
        skill_id=skill.id,
        user_id=user_id,
        note="v0.5.1.1 will call cgi-bin/message/send text+button",
    )
    return False


# ─── 回执通知 (sign / reject / expired) ───────────────────


def notify_followup(
    skill: Skill,
    *,
    type_: NotificationType,
    recipient_user_ids: list[str],
    actor_user_id: str | None = None,
) -> int:
    """sign/reject/expired 后给其他 contributor 发 web 通知.

    不走 IM DM (避免噪音), 只在站内铃铛角标 +1.
    Returns: 实际写入条数.
    """
    if type_ == "consent_request":
        raise ValueError("notify_followup 仅用于 signed/rejected/expired")
    title_map = {
        "consent_signed": f"✅ Skill《{skill.name}》新签字",
        "consent_rejected": f"❌ Skill《{skill.name}》被拒",
        "consent_expired": f"⏰ Skill《{skill.name}》同意超时",
    }
    body_map: dict[str, str] = {
        "consent_signed": (
            f"{actor_user_id or '某 contributor'} 已签字; "
            f"全员签后将进入 draft 待发布."
        ),
        "consent_rejected": (
            f"{actor_user_id or '某 contributor'} 拒绝, "
            f"该 Skill 已冻结归档."
        ),
        "consent_expired": "30 天无响应, 该 Skill 已自动归档为 expired_no_consent.",
    }
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"
    now = datetime.now(timezone.utc)
    count = 0
    for uid in recipient_user_ids:
        notif = WebNotification(
            id=f"notif-{uuid.uuid4().hex[:12]}",
            user_id=uid,
            type=type_,
            title=title_map[type_],
            body=body_map[type_],
            link_url=link,
            read=False,
            created_at=now,
            related_skill_id=skill.id,
        )
        try:
            _persist_notification(notif)
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "consent_followup_notify_failed",
                skill_id=skill.id,
                user_id=uid,
                type=type_,
                error=str(e),
            )
    return count


__all__ = [
    "NotifyReport",
    "build_feishu_card",
    "notify_all",
    "notify_followup",
]
