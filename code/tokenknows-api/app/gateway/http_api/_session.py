"""FastAPI 依赖: 从请求头解出当前 session user.

v1.1 (T75): 优先 JWT Bearer; 退 X-User-Id header (backward-compat).
v0.9 (T66): MVP X-User-Id header (待 v1.1 替换).

未来 (v1.2): 移除 X-User-Id 支持, 仅 JWT.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.services.auth.token import AuthError, get_user_id_from_token


def _try_decode_bearer(authorization: str | None) -> str | None:
    """从 Authorization header 解 Bearer JWT; 失败返 None."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
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
