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
from datetime import UTC, datetime
from typing import Any

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
    """单条 web 通知 (consent_request 类型) + SSE 推送."""
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
        created_at=datetime.now(UTC),
        related_skill_id=skill.id,
    )
    _persist_notification(notif)
    # T53: 实时推送给已订阅 SSE 的客户端 (best-effort)
    _publish_sse_notification(notif, skill_id=skill.id)
    return notif


def _publish_sse_notification(
    notif: WebNotification,
    *,
    skill_id: str | None = None,
    extra: dict | None = None,
) -> None:
    """统一 SSE 推送入口 (try-except 不阻塞主路径)."""
    try:
        # v1.0.1: 去掉重复 import (store_module 已在模块顶层导入)
        from app.services import notification_sse
        from app.services.notification_sse import SseNotificationEvent

        unread = store_module.get_db().count_unread_notifications(notif.user_id)
        ev = SseNotificationEvent(
            event=notif.type,
            user_id=notif.user_id,
            skill_id=skill_id or notif.related_skill_id,
            notification_id=notif.id,
            unread_count=unread,
            extra=extra,
        )
        notification_sse.publish_to_user(notif.user_id, ev)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "consent_sse_publish_failed",
            user_id=notif.user_id,
            notif_id=notif.id,
            error=str(e),
        )


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


# ─── 钉钉 ActionCard (T55 实装) ────────────────────────────


_DINGTALK_API_BASE = "https://oapi.dingtalk.com"


def _send_dm_dingtalk_stub(
    connection_raw: dict, skill: Skill, user_id: str
) -> bool:
    """POST /topapi/message/corpconversation/asyncsend_v2 (工作通知).

    https://open.dingtalk.com/document/orgapp/asynchronous-sending-of-enterprise-session-messages
    Body: msgtype=action_card, action_card with 2 btn_json_list (sign/reject).

    需 connection_raw 含 agent_id (钉钉企业内部应用 id);
    缺 agent_id → degrade to stub (返 False, web fallback 已写).
    保留 _stub 名以保持向后兼容 (路由表不动).
    """
    auth_enc = connection_raw.get("auth_token_enc")
    agent_id = connection_raw.get("agent_id") or connection_raw.get(
        "dingtalk_agent_id"
    )
    if not auth_enc:
        logger.warning("consent_dm_dingtalk_no_token", skill_id=skill.id)
        return False
    if not agent_id:
        logger.info(
            "consent_dm_dingtalk_no_agent_id",
            skill_id=skill.id,
            note="connection_raw 缺 agent_id; degrade to web fallback only",
        )
        return False
    try:
        access_token = decrypt_token(auth_enc)
    except TokenCryptoError as e:
        logger.warning(
            "consent_dm_dingtalk_decrypt_failed",
            skill_id=skill.id, error=str(e),
        )
        return False

    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    detail = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"
    card = build_dingtalk_action_card(skill, detail_url=detail)

    url = f"{_DINGTALK_API_BASE}/topapi/message/corpconversation/asyncsend_v2"
    body = {
        "agent_id": agent_id,
        "userid_list": user_id,
        "msg": {"msgtype": "action_card", "action_card": card},
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            url, params={"access_token": access_token}, json=body
        )
    if resp.status_code != 200:
        logger.warning(
            "consent_dm_dingtalk_http_error",
            status=resp.status_code, body=resp.text[:200],
        )
        return False
    data = resp.json()
    if data.get("errcode", 0) != 0:
        logger.warning(
            "consent_dm_dingtalk_api_error",
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        return False
    logger.info(
        "consent_dm_dingtalk_ok",
        skill_id=skill.id, user_id=user_id,
        task_id=data.get("task_id"),
    )
    return True


def build_dingtalk_action_card(
    skill: Skill, *, detail_url: str
) -> dict[str, Any]:
    """钉钉 ActionCard 模板 (双按钮 sign/reject)."""
    return {
        "title": f"🤖 Skill 草稿等待你确认 · {skill.name}",
        "markdown": (
            f"### {skill.name}\n\n"
            f"基于最近研发讨论 (含 {len(skill.contributors)} 位贡献者), "
            f"自动蒸馏出 Skill 草稿.\n\n"
            f"请选择是否同意发布到项目知识库.\n\n"
            f"_30 天内未响应将自动归档为 expired_no_consent._"
        ),
        "btn_orientation": "1",  # 横向并排
        "btn_json_list": [
            {"title": "✅ 同意发布", "action_url": f"{detail_url}?action=sign"},
            {"title": "❌ 拒绝", "action_url": f"{detail_url}?action=reject"},
        ],
    }


# ─── 企微 textcard (T55 实装, 整卡单链接 degrade) ──────────


_WEWORK_API_BASE = "https://qyapi.weixin.qq.com"


def _send_dm_wework_stub(
    connection_raw: dict, skill: Skill, user_id: str
) -> bool:
    """POST /cgi-bin/message/send (企业应用消息).

    https://developer.work.weixin.qq.com/document/path/90236
    msgtype=textcard: 整个卡片单链接, 跳到 web detail 让用户选 sign/reject.
    (企微 textcard 不支持多按钮; template_card 需要更复杂权限.)

    缺 agentid → degrade.
    """
    auth_enc = connection_raw.get("auth_token_enc")
    agentid = connection_raw.get("agentid") or connection_raw.get(
        "wework_agentid"
    )
    if not auth_enc:
        logger.warning("consent_dm_wework_no_token", skill_id=skill.id)
        return False
    if not agentid:
        logger.info(
            "consent_dm_wework_no_agentid",
            skill_id=skill.id,
            note="connection_raw 缺 agentid; degrade to web fallback only",
        )
        return False
    try:
        access_token = decrypt_token(auth_enc)
    except TokenCryptoError as e:
        logger.warning(
            "consent_dm_wework_decrypt_failed",
            skill_id=skill.id, error=str(e),
        )
        return False

    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    detail = f"{base}/skills/{skill.id}" if base else f"/skills/{skill.id}"
    card = build_wework_textcard(skill, detail_url=detail)

    url = f"{_WEWORK_API_BASE}/cgi-bin/message/send"
    body = {
        "touser": user_id,
        "msgtype": "textcard",
        "agentid": agentid,
        "textcard": card,
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            url, params={"access_token": access_token}, json=body
        )
    if resp.status_code != 200:
        logger.warning(
            "consent_dm_wework_http_error",
            status=resp.status_code, body=resp.text[:200],
        )
        return False
    data = resp.json()
    if data.get("errcode", 0) != 0:
        logger.warning(
            "consent_dm_wework_api_error",
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        return False
    logger.info(
        "consent_dm_wework_ok",
        skill_id=skill.id, user_id=user_id,
        msgid=data.get("msgid"),
    )
    return True


def build_wework_textcard(skill: Skill, *, detail_url: str) -> dict[str, Any]:
    """企微 textcard 模板 (整卡单链接).

    sign/reject 由跳转的 web 页二选一 (企微 textcard 不支持多按钮).
    """
    return {
        "title": "🤖 Skill 草稿等待确认",
        "description": (
            f"<div class=\"highlight\">{skill.name}</div>"
            f"<div class=\"normal\">"
            f"基于最近 {len(skill.contributors)} 位贡献者的研发讨论自动蒸馏. "
            f"点击查看并选择同意/拒绝.</div>"
        ),
        "url": detail_url,
        "btntxt": "查看详情",
    }


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
    now = datetime.now(UTC)
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
            _publish_sse_notification(
                notif,
                skill_id=skill.id,
                extra={"actor_user_id": actor_user_id} if actor_user_id else None,
            )
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "consent_followup_notify_failed",
                skill_id=skill.id,
                user_id=uid,
                notif_type=type_,
                error=str(e),
            )
    return count


__all__ = [
    "NotifyReport",
    "build_dingtalk_action_card",
    "build_feishu_card",
    "build_wework_textcard",
    "notify_all",
    "notify_followup",
]
