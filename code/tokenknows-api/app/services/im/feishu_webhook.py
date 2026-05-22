"""飞书 Webhook 接入 · AES 解密 + 签名验证 + challenge response + 消息入库.

来源:
- engineering_handoff/tasks/T19-feishu-messaging.md §4 Webhook 链路
- Proposal §9.3 飞书适配器
- 飞书开放平台事件订阅 v2 文档

飞书 webhook 请求结构 (Event Subscription v2):
  Headers:
    X-Lark-Request-Timestamp: 秒级
    X-Lark-Request-Nonce: 随机字符串
    X-Lark-Signature: SHA256( timestamp + nonce + encrypt_key + body ).hex()
  Body (加密时):
    { "encrypt": "<base64 ciphertext>" }
  Body (未加密时, 仅 url_verification 才允许):
    { "schema": "2.0", "header": {...}, "event": {...} }
    OR
    { "type": "url_verification", "challenge": "xxx" }

解密:
  AES-256-CBC, key = SHA256(encrypt_key).digest()[:32], IV = ciphertext[:16],
  PKCS#7 padding. 解密结果是上面"未加密"格式的 JSON.

挑战响应:
  type == "url_verification" → return {"challenge": payload["challenge"]}

消息事件:
  event.type == "im.message.receive_v1" → 写 im_messages 表
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config.logging import logger
from app.config.settings import get_settings
from app.persistence import get_db
from app.schemas.im import IMUser
from app.services import im_service
from app.services.im import retention
from app.services.im.connector_base import IMNormalizedMessage
from app.services.im.signal_gate import classify_message


class FeishuWebhookError(Exception):
    """webhook 处理失败基类."""


class SignatureMismatch(FeishuWebhookError):
    """X-Lark-Signature 验证失败."""


class DecryptError(FeishuWebhookError):
    """AES 解密失败."""


# ─── 解密 ────────────────────────────────────────────────────


def decrypt_payload(encrypted_b64: str, encrypt_key: str) -> dict:
    """AES-256-CBC 解密飞书加密 payload.

    Args:
        encrypted_b64: payload['encrypt'] 字段 (URL-safe-base64)
        encrypt_key: FEISHU_ENCRYPT_KEY (任意长度字符串, SHA256 后取 32 字节作 AES key)

    Returns:
        解密后的 JSON dict.

    Raises:
        DecryptError: base64/AES/JSON 任一步失败.
    """
    try:
        # 飞书用标准 base64, 不是 url-safe
        cipher_bytes = base64.b64decode(encrypted_b64)
    except (ValueError, base64.binascii.Error) as e:
        raise DecryptError(f"base64 解码失败: {e}") from e
    if len(cipher_bytes) < 32:
        raise DecryptError(f"密文太短: {len(cipher_bytes)} 字节")

    # AES key = sha256(encrypt_key)
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    # 飞书的密文格式: 前 16 字节 IV + 后面是密文
    iv = cipher_bytes[:16]
    body = cipher_bytes[16:]

    try:
        from cryptography.hazmat.primitives.ciphers import (
            Cipher, algorithms, modes
        )
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(body) + decryptor.finalize()
    except Exception as e:
        raise DecryptError(f"AES 解密失败: {e}") from e

    # PKCS#7 unpad
    if not decrypted:
        raise DecryptError("解密结果为空")
    pad_len = decrypted[-1]
    if pad_len < 1 or pad_len > 16:
        raise DecryptError(f"PKCS#7 padding 非法: {pad_len}")
    unpadded = decrypted[:-pad_len]

    try:
        return json.loads(unpadded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DecryptError(f"解密后非合法 JSON: {e}") from e


# ─── 签名验证 ────────────────────────────────────────────────


def compute_signature(
    timestamp: str, nonce: str, encrypt_key: str, raw_body: bytes
) -> str:
    """飞书签名算法: sha256(timestamp + nonce + encrypt_key + body).hexdigest()."""
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(nonce.encode("utf-8"))
    h.update(encrypt_key.encode("utf-8"))
    h.update(raw_body)
    return h.hexdigest()


def verify_signature(
    timestamp: str,
    nonce: str,
    signature: str,
    encrypt_key: str,
    raw_body: bytes,
) -> bool:
    """常量时间比较."""
    expected = compute_signature(timestamp, nonce, encrypt_key, raw_body)
    return hmac.compare_digest(expected, signature)


# ─── 消息事件入库 ────────────────────────────────────────────


def _parse_event_message(
    event_payload: dict, connection_id: str
) -> IMNormalizedMessage | None:
    """飞书 im.message.receive_v1 event → IMNormalizedMessage. None=跳过."""
    msg = event_payload.get("message") or {}
    sender_raw = event_payload.get("sender") or {}
    chat_id = msg.get("chat_id") or msg.get("root_id") or ""
    msg_id = msg.get("message_id") or ""
    if not chat_id or not msg_id:
        return None

    msg_type = msg.get("message_type")
    if msg_type and msg_type not in ("text", "post", "interactive"):
        return None

    # content 是 JSON 字符串
    raw_content = msg.get("content") or "{}"
    try:
        content_obj = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except json.JSONDecodeError:
        content_obj = {"text": raw_content}
    text = content_obj.get("text") or ""
    if not text.strip():
        return None

    # sender
    sender_id_obj = sender_raw.get("sender_id") or {}
    sender = IMUser(
        user_id=sender_id_obj.get("open_id") or sender_id_obj.get("user_id") or "",
        name=sender_raw.get("name"),
    )

    # mentions
    mentions: list[str] = []
    for m in msg.get("mentions") or []:
        oid_obj = m.get("id") or {}
        if isinstance(oid_obj, dict):
            oid = oid_obj.get("open_id") or oid_obj.get("user_id")
        else:
            oid = str(oid_obj)
        if oid:
            mentions.append(oid)

    # 时间戳: 飞书 create_time 是毫秒字符串
    ts_raw = msg.get("create_time")
    received = datetime.now(timezone.utc)
    try:
        if ts_raw:
            received = datetime.fromtimestamp(int(ts_raw) / 1000, tz=timezone.utc)
    except (ValueError, TypeError):
        pass

    return IMNormalizedMessage(
        platform="feishu",
        platform_chat_id=chat_id,
        platform_msg_id=msg_id,
        sender=sender,
        content=text,
        mentions=mentions,
        received_at=received,
        raw_event_type=msg_type or "message",
    )


def store_message(
    connection_id: str, normalized: IMNormalizedMessage
) -> bool:
    """写 im_messages 表 + 计算 retention_until + SignalGate.

    Returns:
        True=新增 / False=已存在 (幂等).
    """
    db = get_db()
    retention_until = retention.compute_retention_until(normalized.received_at)
    # SignalGate (无上下文 - webhook 是单条流式, 上下文待 batch 蒸馏时补)
    signal = classify_message(normalized)

    from app.schemas.im import IMMessage
    msg = IMMessage(
        id=f"im-msg-{uuid.uuid4().hex[:12]}",
        connection_id=connection_id,
        platform_chat_id=normalized.platform_chat_id,
        platform_msg_id=normalized.platform_msg_id,
        sender=normalized.sender,
        content=normalized.content,
        mentions=normalized.mentions,
        is_signal=signal.is_signal,
        received_at=normalized.received_at,
        retention_until=retention_until,
        redacted=False,
    )
    inserted = db.insert_im_message(
        message_id=msg.id,
        connection_id=connection_id,
        platform_chat_id=msg.platform_chat_id,
        platform_msg_id=msg.platform_msg_id,
        received_at=msg.received_at.isoformat(),
        retention_until=retention_until.isoformat(),
        is_signal=msg.is_signal,
        redacted=False,
        json_str=msg.model_dump_json(),
    )
    return inserted


# ─── 主分发器 ────────────────────────────────────────────────


def find_connection_by_tenant_key(tenant_key: str):
    """根据 tenant_key 路径参数找对应 IMConnection.

    所有 active 飞书 connection 中, tenant_name 等于 tenant_key 的取首条.
    多 tenant 同名时返第一个 active.
    """
    # 简单实现: 扫所有飞书 connection, MVP 单实例规模可接受
    db = get_db()
    rows = db.load_all_im_connections()
    for row in rows:
        if (
            row.get("platform") == "feishu"
            and row.get("status") == "active"
            and (row.get("tenant_name") == tenant_key)
        ):
            return im_service.get_connection(row["id"])
    return None


def process_event_payload(
    payload: dict, tenant_key: str
) -> dict[str, Any]:
    """主入口: 处理已解密的 payload.

    Returns:
        要返给飞书的响应 JSON dict.
    """
    # 1. URL verification challenge
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not challenge:
            raise FeishuWebhookError("url_verification 缺 challenge 字段")
        return {"challenge": challenge}

    # 2. 普通事件
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("event_type")
    event = payload.get("event") or {}

    if event_type != "im.message.receive_v1":
        # 暂只处理消息接收事件; 其它静默
        logger.info("feishu_webhook_event_ignored", event_type=event_type)
        return {"ok": True, "note": f"event_type {event_type} not handled"}

    conn = find_connection_by_tenant_key(tenant_key)
    if conn is None:
        logger.warning("feishu_webhook_no_connection", tenant_key=tenant_key)
        return {"ok": False, "note": "no active connection for tenant"}

    normalized = _parse_event_message(event, conn.id)
    if normalized is None:
        return {"ok": True, "note": "message skipped (non-text or empty)"}

    inserted = store_message(conn.id, normalized)
    logger.info(
        "feishu_webhook_message_stored",
        connection=conn.id,
        chat=normalized.platform_chat_id,
        msg=normalized.platform_msg_id,
        is_signal=classify_message(normalized).is_signal,
        new=inserted,
    )
    return {"ok": True, "stored": inserted}


def handle_webhook(
    raw_body: bytes,
    tenant_key: str,
    timestamp: str | None,
    nonce: str | None,
    signature: str | None,
) -> dict[str, Any]:
    """完整 webhook 处理.

    Args:
        raw_body: 请求 body (字节级, 用于签名验证)
        tenant_key: 路径参数 (路由提供)
        timestamp / nonce / signature: 来自 headers

    Returns:
        要返给飞书的 JSON dict.

    Raises:
        SignatureMismatch / DecryptError / FeishuWebhookError
    """
    settings = get_settings()
    encrypt_key = settings.feishu_encrypt_key

    # 1. 验证签名 (encrypt_key 配置时)
    if encrypt_key and signature:
        if not (timestamp and nonce):
            raise SignatureMismatch("缺 timestamp / nonce header")
        if not verify_signature(
            timestamp, nonce, signature, encrypt_key, raw_body
        ):
            raise SignatureMismatch("X-Lark-Signature 不匹配")

    # 2. 解析 body
    try:
        outer = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FeishuWebhookError(f"body 非合法 JSON: {e}") from e

    # 3. 解密 (encrypt 字段存在 + encrypt_key 配置时)
    if "encrypt" in outer:
        if not encrypt_key:
            raise DecryptError(
                "payload 有 encrypt 字段但 FEISHU_ENCRYPT_KEY 未配置"
            )
        payload = decrypt_payload(outer["encrypt"], encrypt_key)
    else:
        payload = outer

    # 4. 分发处理
    return process_event_payload(payload, tenant_key)
