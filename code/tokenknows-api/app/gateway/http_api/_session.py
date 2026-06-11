"""FastAPI 依赖: 从请求头解出当前 session user.

v2.1: Bearer 同时支持 PAT (`tkk_` 前缀) 与 JWT; 新增 auth_mode 强制依赖.
v1.1 (T75): 优先 JWT Bearer; 退 X-User-Id header (backward-compat).
v0.9 (T66): MVP X-User-Id header (待 v1.1 替换).

未来 (v1.2): 移除 X-User-Id 支持, 仅 JWT / PAT.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config.settings import get_settings
from app.services.auth import pat_service
from app.services.auth.token import AuthError, get_user_id_from_token


def _try_decode_bearer(authorization: str | None) -> str | None:
    """从 Authorization header 解 Bearer token (PAT 或 JWT); 失败返 None."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    # v2.1: tkk_ 前缀 → PAT 路径 (sha256 lookup, 无效返 None)
    if token.startswith(pat_service.TOKEN_PREFIX):
        return pat_service.verify_token(token)
    try:
        return get_user_id_from_token(token)
    except AuthError:
        return None


async def get_current_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str | None:
    """非强制版本: 解 Authorization Bearer JWT; 退 X-User-Id; 都缺返 None.

    使用场景: 允许某些路径不传 session 的 backward-compat endpoint.
    """
    # 优先 JWT (v1.1+ 推荐)
    user_id = _try_decode_bearer(authorization)
    if user_id:
        return user_id
    # backward-compat: X-User-Id 直接信任 (v0.9 MVP)
    if x_user_id:
        cleaned = x_user_id.strip()
        return cleaned or None
    return None


async def require_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """强制版本: 解 JWT 或 X-User-Id; 都缺/无效 → 401."""
    user_id = _try_decode_bearer(authorization)
    if user_id:
        return user_id
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    # 401 + WWW-Authenticate 提示 Bearer
    raise HTTPException(
        401,
        detail="Authentication required (Bearer JWT or X-User-Id header)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_verified_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """强认证版本: 仅认 Bearer (JWT / PAT), 不退 X-User-Id.

    用于凭证签发等高敏端点 — X-User-Id 是 trust-on-faith header,
    若允许它创建 PAT 等于把伪造头升级成长期凭证 (account takeover).
    """
    user_id = _try_decode_bearer(authorization)
    if user_id:
        return user_id
    raise HTTPException(
        401,
        detail="Authentication required (Bearer JWT or PAT)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth_if_required(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """v2.1 · AUTH_MODE 门禁依赖 (挂在数据 router 上).

    - auth_mode='open' (默认): 放行; 但带了 Bearer 仍解一次 — PAT 的
      last_used_at ("插件已连上"信号) 在默认部署下才真实可用.
    - auth_mode='required': 仅认 Bearer (JWT / PAT); X-User-Id 不算认证
      (它是 trust-on-faith header, required 模式下不可伪造放行) → 401.
    """
    if get_settings().auth_mode == "open":
        if authorization:
            _try_decode_bearer(authorization)
        return
    if _try_decode_bearer(authorization):
        return
    raise HTTPException(
        401,
        detail="Authentication required (Bearer JWT or PAT)",
        headers={"WWW-Authenticate": "Bearer"},
    )
