"""IM access_token 自动后台刷新 (v0.3.1 I).

设计:
- 后台 task 每 10 分钟扫一次所有 active connection
- 找 token_expires_at <= now + 5 分钟的 → 调 connector.refresh_token
- 成功: 调 im_service.apply_oauth_result 更新 token + 持久化
- 失败: 标 connection.status = "revoked" + 让用户重新 OAuth

不在范围:
- token 加密轮换 (留 v0.4)
- 钉钉 / 企微 refresh_token (本任务只覆盖飞书 + 通用骨架)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config.logging import logger
from app.schemas.im import IMConnection
from app.services import im_crypto, im_service
from app.services.im.connector_base import (
    OAuthExchangeError,
    OAuthExchangeResult,
    TokenExpiredError,
)

# 提前 N 分钟刷新; 飞书 token 默认 2 小时, 提前 5 分钟够缓冲网络抖动.
REFRESH_AHEAD = timedelta(minutes=5)
DEFAULT_INTERVAL_SECONDS = 600   # 10 分钟


def list_due_connections(now: datetime | None = None) -> list[IMConnection]:
    """找所有需要刷新的 connection.

    条件:
        status == active AND
        token_expires_at IS NOT NULL AND
        token_expires_at <= now + REFRESH_AHEAD AND
        refresh_token_enc IS NOT NULL  (没 refresh token 没法刷)
    """
    now_dt = now or datetime.now(UTC)
    threshold = now_dt + REFRESH_AHEAD
    out: list[IMConnection] = []
    # 遍历各项目的 active connection
    seen: set[str] = set()
    for conn in im_service.get_registry()._cache.values():
        if conn.id in seen:
            continue
        seen.add(conn.id)
        if conn.status != "active":
            continue
        if not conn.token_expires_at:
            continue
        if not conn.refresh_token_enc:
            continue
        if conn.token_expires_at <= threshold:
            out.append(conn)
    return out


async def refresh_one(conn: IMConnection) -> tuple[bool, str | None]:
    """对单个 connection 刷 token.

    Returns:
        (成功?, 错误描述 / None)
    """
    try:
        refresh_plain = im_crypto.decrypt_token(conn.refresh_token_enc or "")
    except im_crypto.TokenCryptoError as e:
        # 密钥变了或密文坏 → 标 revoked
        logger.warning(
            "im_refresh_decrypt_failed", id=conn.id, error=str(e)
        )
        im_service.update_status(conn.id, "revoked")
        return False, f"decrypt: {e}"

    instance = im_service.build_connector(conn)
    try:
        result: OAuthExchangeResult = await instance.refresh_token(refresh_plain)
    except TokenExpiredError as e:
        logger.warning("im_refresh_token_expired", id=conn.id, error=str(e))
        im_service.update_status(conn.id, "revoked")
        return False, f"refresh_token expired: {e}"
    except OAuthExchangeError as e:
        logger.warning("im_refresh_provider_error", id=conn.id, error=str(e))
        return False, f"provider: {e}"
    except Exception as e:
        logger.error("im_refresh_unexpected", id=conn.id, error=str(e))
        return False, f"unexpected: {e}"

    im_service.apply_oauth_result(conn.id, result)
    logger.info(
        "im_token_refreshed",
        id=conn.id, platform=conn.platform,
        new_expires_at=result.expires_at.isoformat() if result.expires_at else None,
    )
    return True, None


async def refresh_due_tokens(now: datetime | None = None) -> dict[str, int]:
    """一次性扫 + 刷. 返回统计 (供监控)."""
    due = list_due_connections(now)
    succeeded = 0
    failed = 0
    for conn in due:
        ok, _ = await refresh_one(conn)
        if ok:
            succeeded += 1
        else:
            failed += 1
    if due:
        logger.info(
            "im_token_refresher_swept",
            checked=len(due), ok=succeeded, failed=failed,
        )
    return {"checked": len(due), "ok": succeeded, "failed": failed}


async def token_refresher_loop(
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """长期后台 task; main.py lifespan 调用."""
    while True:
        try:
            await refresh_due_tokens()
        except Exception as e:
            logger.error("im_token_refresher_failed", error=str(e))
        await asyncio.sleep(interval_seconds)
