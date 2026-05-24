"""RejectNotifier · T130 MVP · 章节退回 → 作者 IM DM.

只支持飞书 (复用 v0.5.1 consent_notifier._send_dm_feishu 模式).
钉钉/企微待后续 T130.2/T130.3.

设计 (与 consent_notifier 同风格):
- sync 调用 (与 reject_chapter 同步路径一致, 不阻塞主流程)
- 任何异常 swallow + log warning, 不影响 reject_chapter 写状态
- author 识别: asset.created_by 形如 'ou_xxx' 视为 Feishu open_id 才发
  (MVP 简化: 不引入 user → IM 映射表; 现实里 plugin/web 创 asset 时
  若已用 open_id 当作 author, 直接复用; 否则跳过留给 web SSE 通道兜底)
- 项目级 active 飞书 connection 不存在 → 跳过, log info
- 没 public_base_url 配 → button URL 用相对路径 (飞书客户端按本机域名打开)

公共入口:
    notify_chapter_rejected(asset, chapter, reason) -> NotifyResult
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config.logging import logger
from app.config.settings import get_settings
from app.schemas.asset import Asset, Chapter
from app.services import im_service
from app.services.im_crypto import TokenCryptoError, decrypt_token


_HTTP_TIMEOUT = 10.0
_FEISHU_OPENID_PREFIX = "ou_"


@dataclass(frozen=True)
class NotifyResult:
    """notify_chapter_rejected 的可观测返回."""

    sent: bool
    """飞书 DM 真发出去 (HTTP 2xx + API code=0)."""

    skipped_reason: str | None = None
    """sent=False 时记录跳过原因; sent=True 时为 None."""

    platform: str | None = None
    """实际使用的 IM 平台 (目前固定 'feishu' 或 None)."""


def notify_chapter_rejected(
    asset: Asset, chapter: Chapter, reason: str
) -> NotifyResult:
    """章节退回 → 给作者发飞书 DM 卡片 (sync).

    完全 best-effort: 任何失败仅 log warning, 永远返回 NotifyResult (不抛).
    """
    try:
        return _notify_inner(asset, chapter, reason)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reject_notifier_unexpected_error",
            asset_id=asset.id,
            chapter_id=chapter.id,
            error=str(exc),
        )
        return NotifyResult(sent=False, skipped_reason="unexpected_error")


def _notify_inner(asset: Asset, chapter: Chapter, reason: str) -> NotifyResult:
    author = (asset.created_by or "").strip()
    # MVP 守卫 1: 匿名 / 空作者 → 没人收
    if not author or author == "anonymous":
        return NotifyResult(sent=False, skipped_reason="anonymous_author")

    # MVP 守卫 2: 不是飞书 open_id 形态 → 当前 MVP 不做 user→open_id 映射,
    # 留 SSE 通道兜底; 后续 T130.4 引入 ProjectMember 绑定后这里可放宽.
    if not author.startswith(_FEISHU_OPENID_PREFIX):
        return NotifyResult(sent=False, skipped_reason="author_not_feishu_openid")

    # 找项目下 active 飞书连接
    conns = im_service.list_connections(asset.project_id, status="active")
    feishu_conn = next((c for c in conns if c.platform == "feishu"), None)
    if feishu_conn is None:
        return NotifyResult(sent=False, skipped_reason="no_active_feishu_connection")

    # 解密 token (失败 → swallow)
    if not feishu_conn.auth_token_enc:
        return NotifyResult(sent=False, skipped_reason="connection_no_token")
    try:
        access_token = decrypt_token(feishu_conn.auth_token_enc)
    except TokenCryptoError as e:
        logger.warning(
            "reject_dm_feishu_decrypt_failed",
            asset_id=asset.id,
            error=str(e),
        )
        return NotifyResult(sent=False, skipped_reason="token_decrypt_failed")

    card = build_reject_card_feishu(asset, chapter, reason)
    ok = _send_feishu_dm(
        access_token=access_token,
        open_id=author,
        card=card,
        asset_id=asset.id,
        chapter_id=chapter.id,
    )
    return NotifyResult(
        sent=ok,
        skipped_reason=None if ok else "feishu_http_error",
        platform="feishu",
    )


def _send_feishu_dm(
    *,
    access_token: str,
    open_id: str,
    card: dict[str, Any],
    asset_id: str,
    chapter_id: str,
) -> bool:
    """POST /open-apis/im/v1/messages?receive_id_type=open_id, msg_type=interactive."""
    settings = get_settings()
    url = (
        f"{settings.feishu_api_base.rstrip('/')}"
        f"/open-apis/im/v1/messages?receive_id_type=open_id"
    )
    body = {
        "receive_id": open_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        logger.warning(
            "reject_dm_feishu_network_error",
            asset_id=asset_id,
            chapter_id=chapter_id,
            error=str(e),
        )
        return False

    if resp.status_code != 200:
        logger.warning(
            "reject_dm_feishu_http_error",
            asset_id=asset_id,
            chapter_id=chapter_id,
            status=resp.status_code,
            body=resp.text[:200],
        )
        return False
    try:
        data = resp.json()
    except ValueError:
        logger.warning(
            "reject_dm_feishu_invalid_json",
            asset_id=asset_id,
            body=resp.text[:200],
        )
        return False
    if data.get("code") not in (0, None):
        logger.warning(
            "reject_dm_feishu_api_error",
            asset_id=asset_id,
            code=data.get("code"),
            msg=data.get("msg"),
        )
        return False
    logger.info(
        "reject_dm_feishu_ok",
        asset_id=asset_id,
        chapter_id=chapter_id,
        open_id=open_id,
        message_id=(data.get("data") or {}).get("message_id"),
    )
    return True


def build_reject_card_feishu(
    asset: Asset, chapter: Chapter, reason: str
) -> dict[str, Any]:
    """构造飞书 interactive card · "章节被退回" 模板.

    public_base_url 未配时 button 用相对路径.
    """
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    doc_path = f"/projects/{asset.project_id}/documents/{asset.id}"
    detail_url = f"{base}{doc_path}" if base else doc_path

    type_label = {
        "weekly_report": "周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策",
        "incident": "故障复盘",
        "book": "技术手册",
        "agent_skill": "Agent 技能",
        "knowledge_graph": "知识图谱",
    }.get(asset.type, asset.type)

    # 截断超长 reason / title 防卡片爆字 (飞书 lark_md 上限 ~ 5KB)
    safe_reason = reason if len(reason) <= 500 else reason[:500] + "…"
    asset_title = asset.title or "(无标题)"
    chapter_title = chapter.title or f"§{chapter.order_index + 1}"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "📋 你的章节被退回",
            },
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**文档类型**\n{type_label}",
                        },
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**退回章节**\n§{chapter.order_index + 1} {chapter_title}",
                        },
                    },
                ],
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**文档**: {asset_title}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**审批人退回理由**:\n{safe_reason}",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "打开文档修订",
                        },
                        "type": "primary",
                        "url": detail_url,
                    },
                ],
            },
        ],
    }


__all__ = [
    "NotifyResult",
    "build_reject_card_feishu",
    "notify_chapter_rejected",
]
