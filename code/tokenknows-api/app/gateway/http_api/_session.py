"""FastAPI 依赖: 从请求头解出当前 session user (v0.9.0 T66).

MVP: 用 X-User-Id header (trust-on-faith 但比 body 字段更难伪造);
生产换为 JWT Bearer / Cookie session.

Backward-compat:
- 未传 X-User-Id 时返 None, endpoint 内自行决定是否拒绝 (401)
- review/approve 等强校验 endpoint 用 require_user_id() 拒缺失
"""

from __future__ import annotations

from fastapi import Header, HTTPException


async def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str | None:
    """非强制版本: 返 None 不抛.

    使用场景: backward-compat endpoint, 允许某些路径不传 header.
    """
    if x_user_id is None:
        return None
    cleaned = x_user_id.strip()
    return cleaned or None


async def require_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """强制版本: 缺 X-User-Id → 401.

    使用场景: review/approve/reject 等敏感操作 endpoint.
    """
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            401, detail="X-User-Id header required for this operation"
        )
    return x_user_id.strip()
