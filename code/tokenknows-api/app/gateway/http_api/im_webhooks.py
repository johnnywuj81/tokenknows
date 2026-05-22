"""IM 集成 webhook + OAuth callback HTTP endpoints (v0.3 T18+).

包含:
- POST /webhooks/feishu/auth-callback: 飞书 OAuth 跳回 (T18)
- POST /webhooks/feishu/events/{tenant_key}: 飞书消息 webhook (T19, 占位)
- (后续 T19/T20 在此扩展)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config.logging import logger
from app.services import im_service
from app.services.im import feishu_connector  # noqa: F401 注册副作用
from app.services.im.connector_base import (
    ConnectorError,
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
