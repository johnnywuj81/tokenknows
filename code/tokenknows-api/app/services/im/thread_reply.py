"""IM 群内 Thread 回执 · v0.5.0 T47.

让 @ 机器人触发的 mention 在原 thread 内回执,
保持群内对话透明 (Proposal v0.5 OD-5).

设计:
- sync 接口 (与 mention_dispatcher / feishu_webhook 同步路径自然衔接)
- 失败兜底: 全部异常 catch + log warning, 不抛给 caller
  (asset 已生成不能回滚; 回执失败不阻塞主流程)
- 飞书完整实现; 钉钉/企微 v0.5.0 stub 仅 log
  (v0.5.0.1 接入 钉钉 robot/groupMessages/send + 企微 send_to_chat with quote)

API:
- POST /open-apis/im/v1/messages 飞书 (msg_type=text + reply_in_thread=true + ref_id=parent)

decrypt access_token 复用 im_crypto.decrypt_token.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config.logging import logger
from app.config.settings import get_settings
from app.services.im_crypto import TokenCryptoError, decrypt_token


_HTTP_TIMEOUT = 10.0  # 短超时, 不阻塞 webhook


def build_reply_text(
    *,
    subcommand: str,
    window: str,
    execution_id: str,
    project_id: str,
    user_id: str | None = None,
) -> str:
    """组装群内回执消息. 含 execution link (若 PUBLIC_BASE_URL 已配).

    Proposal OD-5 风格:
    [Demo] @TokenKnows 收到 /digest 2h
    生成中 (≈ 60s), 查看进度: https://.../executions/<eid>
    """
    by = f" · by {user_id}" if user_id else ""
    base = (
        f"[Demo] @TokenKnows 收到 /{subcommand} {window}{by}\n"
        f"生成中 (≈ 60s)"
    )
    public_base = get_settings().public_base_url
    if public_base:
        url = (
            f"{public_base.rstrip('/')}/projects/{project_id}"
            f"/auto-triggers/executions/{execution_id}"
        )
        base += f"\n查看进度: {url}"
    else:
        base += f"\n查看进度: execution={execution_id} (PUBLIC_BASE_URL 未配置, 无法拼接 link)"
    return base


def reply_in_thread(
    *,
    connection_raw: dict,
    chat_id: str,
    parent_message_id: str,
    text: str,
) -> str | None:
    """根据 connection.platform 路由到对应实现; 返回新发出消息 id.

    Args:
        connection_raw: im_connections 表的 json (含 platform / auth_token_enc).
        chat_id: 飞书 chat_id (oc_xxx) / 钉钉 openConversationId / 企微 chat_id.
        parent_message_id: 原 mention 消息 id (用作 reply parent).
        text: plain text 内容 (build_reply_text 已拼好).

    Returns:
        新消息 id; 失败返 None (已 log).
    """
    platform = connection_raw.get("platform", "")
    try:
        if platform == "feishu":
            return _reply_feishu(connection_raw, chat_id, parent_message_id, text)
        if platform == "dingtalk":
            return _reply_dingtalk_stub(connection_raw, chat_id, parent_message_id, text)
        if platform == "wework":
            return _reply_wework_stub(connection_raw, chat_id, parent_message_id, text)
        logger.warning("thread_reply_unknown_platform", platform=platform)
        return None
    except Exception as e:
        logger.warning(
            "thread_reply_failed",
            platform=platform,
            chat_id=chat_id,
            parent=parent_message_id,
            error=str(e),
        )
        return None


# ─── 飞书 (完整) ──────────────────────────────────────────


def _reply_feishu(
    connection_raw: dict,
    chat_id: str,
    parent_message_id: str,
    text: str,
) -> str | None:
    """POST /open-apis/im/v1/messages?receive_id_type=chat_id.

    body: { receive_id, msg_type='text', content=json({text}), reply_in_thread=true }
    其中 reply 的 parent 通过 URL path /messages/<message_id>/reply 实现 (新版 API).
    """
    auth_enc = connection_raw.get("auth_token_enc")
    if not auth_enc:
        logger.warning("thread_reply_feishu_no_token", chat_id=chat_id)
        return None
    try:
        access_token = decrypt_token(auth_enc)
    except TokenCryptoError as e:
        logger.warning("thread_reply_feishu_decrypt_failed", error=str(e))
        return None

    settings = get_settings()
    url = (
        f"{settings.feishu_api_base.rstrip('/')}"
        f"/open-apis/im/v1/messages/{parent_message_id}/reply"
    )
    body = {
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
        "reply_in_thread": True,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(url, json=body, headers=headers)
    if resp.status_code != 200:
        logger.warning(
            "thread_reply_feishu_http_error",
            status=resp.status_code,
            body=resp.text[:200],
        )
        return None
    data = resp.json()
    if data.get("code") not in (0, None):
        logger.warning(
            "thread_reply_feishu_api_error",
            code=data.get("code"),
            msg=data.get("msg"),
        )
        return None
    new_msg_id = (data.get("data") or {}).get("message_id")
    logger.info(
        "thread_reply_feishu_ok",
        chat_id=chat_id,
        parent=parent_message_id,
        new_msg_id=new_msg_id,
    )
    return new_msg_id


# ─── 钉钉 / 企微 stub (v0.5.0.1 完整接入) ─────────────────


def _reply_dingtalk_stub(
    connection_raw: dict,
    chat_id: str,
    parent_message_id: str,
    text: str,
) -> str | None:
    logger.info(
        "thread_reply_dingtalk_stub",
        chat_id=chat_id,
        parent=parent_message_id,
        text_preview=text[:80],
        note="v0.5.0.1 will call robot/groupMessages/send with originalMessageId",
    )
    return None


def _reply_wework_stub(
    connection_raw: dict,
    chat_id: str,
    parent_message_id: str,
    text: str,
) -> str | None:
    logger.info(
        "thread_reply_wework_stub",
        chat_id=chat_id,
        parent=parent_message_id,
        text_preview=text[:80],
        note="v0.5.0.1 will degrade to send_to_chat with quote (no thread support)",
    )
    return None


__all__ = ["build_reply_text", "reply_in_thread"]
