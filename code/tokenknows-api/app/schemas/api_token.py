"""Personal Access Token schema · v2.1.

MCP / API 客户端的长期凭据 (区别于 24h JWT session token):
- 明文 `tkk_<urlsafe-43>` 仅创建响应返回一次, 永不落库
- DB 只存 sha256(plaintext) + 前 12 字符 prefix (UI 辨识用)
- 撤销 = 软删 (revoked_at 置位), verify 路径只查未撤销行

MVP:
- 不做过期时间 (后续加 expires_at)
- 不做 scope / 权限粒度 (PAT == 该 user 的完整身份)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiToken(BaseModel):
    """PAT entity (内部完整版, 含 token_hash; 永不直接出 API)."""

    id: str
    """pat-{uuid 12 hex}."""

    user_id: str
    name: str = Field(..., min_length=1, max_length=100)
    token_hash: str
    """sha256(plaintext).hexdigest(); 明文不存."""

    token_prefix: str
    """明文前 12 字符 (tkk_ + 8), UI 列表辨识用."""

    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


# ─── 请求 / 响应 DTO ──────────────────────────────────────────────


class ApiTokenPublic(BaseModel):
    """对外不暴露 token_hash / 明文."""

    id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


class CreateApiTokenRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CreateApiTokenResponse(BaseModel):
    """创建成功响应. token 明文仅此一次返回."""

    token: str
    item: ApiTokenPublic


class ApiTokensListResponse(BaseModel):
    items: list[ApiTokenPublic]
