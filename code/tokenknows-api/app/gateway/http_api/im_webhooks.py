"""IM 集成 webhook + OAuth callback HTTP endpoints (v0.3 T18+).

包含:
- GET  /webhooks/feishu/auth-callback: 飞书 OAuth 跳回 (T18)
- POST /webhooks/feishu/events/{tenant_key}: 飞书消息 webhook (v0.3.1 P2)
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.config.logging import logger
from app.services import im_service
from app.services.im import feishu_connector, feishu_webhook  # noqa: F401 注册副作用
from app.services.im.connector_base import (
    OAuthExchangeError,
    registry,
)

router = APIRouter()


@router.get("/webhooks/feishu/auth-callback")
async def feishu_auth_callback(
    code: str = Query(..., description="飞书 OAuth code"),
    state: str = Query(..., description="connection_id"),
) -> dict:
    """飞书 OAuth 完成后跳回此 endpoint.

    state = connection_id (调用方 POST /im/connections 时拿到).
    """
    conn = im_service.get_connection(state)
    if conn is None:
        raise HTTPException(404, detail=f"Connection {state} 不存在")
    if conn.platform != "feishu":
        raise HTTPException(400, detail=f"Connection {state} 不是飞书")
    cls = registry.get("feishu")
    if cls is None:
        raise HTTPException(500, detail="飞书 connector 未注册")
    inst = cls()  # type: ignore[call-arg]
    try:
        result = await inst.exchange_code(code)
    except OAuthExchangeError as e:
        logger.warning("feishu_callback_exchange_failed", state=state, error=str(e))
        # 标 revoked, 前端可以触发重连
        im_service.update_status(state, "revoked")
        raise HTTPException(400, detail=f"OAuth 兑换失败: {e}") from e
    updated = im_service.apply_oauth_result(state, result)
    if updated is None:
        raise HTTPException(500, detail="apply OAuth result 失败")
    logger.info(
        "feishu_oauth_callback_ok",
        connection_id=state,
        tenant=updated.tenant_name,
    )
    return {
        "connection_id": updated.id,
        "status": updated.status,
        "tenant_name": updated.tenant_name,
    }


@router.post("/webhooks/feishu/events/{tenant_key}")
async def feishu_event_webhook(
    tenant_key: str,
    request: Request,
    x_lark_request_timestamp: str | None = Header(default=None),
    x_lark_request_nonce: str | None = Header(default=None),
    x_lark_signature: str | None = Header(default=None),
) -> dict:
    """飞书消息事件 webhook 主入口 (v0.3.1 P2).

    职责:
    1. 验证 X-Lark-Signature (encrypt_key 配置时)
    2. AES 解密 payload['encrypt'] (encrypt_key 配置时)
    3. URL verification challenge → 返 {"challenge": "xxx"}
    4. im.message.receive_v1 → 解析 + SignalGate + 入库 im_messages
    5. 其它 event_type 静默 ok

    tenant_key: 路径参数 (一个 tenant 对应一个 IMConnection.tenant_name)
    """
    raw_body = await request.body()
    try:
        return feishu_webhook.handle_webhook(
            raw_body=raw_body,
            tenant_key=tenant_key,
            timestamp=x_lark_request_timestamp,
            nonce=x_lark_request_nonce,
            signature=x_lark_signature,
        )
    except feishu_webhook.SignatureMismatch as e:
        logger.warning("feishu_webhook_signature_mismatch", error=str(e))
        raise HTTPException(401, detail=str(e)) from e
    except feishu_webhook.DecryptError as e:
        logger.warning("feishu_webhook_decrypt_failed", error=str(e))
        raise HTTPException(400, detail=str(e)) from e
    except feishu_webhook.FeishuWebhookError as e:
        logger.warning("feishu_webhook_bad_request", error=str(e))
        raise HTTPException(400, detail=str(e)) from e
