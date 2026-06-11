"""HTTP API · v2.1 Personal Access Token 管理.

端点:
    POST   /me/tokens               创建 (明文仅此一次返回)
    GET    /me/tokens               列表 (仅 prefix, 不含 hash / 明文)
    DELETE /me/tokens/{token_id}    撤销 (软删)

ACL: 全部走 require_verified_user_id (仅 Bearer JWT/PAT, 不认 X-User-Id
— 伪造头不能签发长期凭证); 只能操作自己的 token.
404 对 "不存在" 与 "非本人" 不做区分 (防 token id 枚举).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.gateway.http_api._session import require_verified_user_id
from app.schemas.api_token import (
    ApiToken,
    ApiTokenPublic,
    ApiTokensListResponse,
    CreateApiTokenRequest,
    CreateApiTokenResponse,
)
from app.services.auth import pat_service

router = APIRouter(tags=["tokens"])


def _to_public(token: ApiToken) -> ApiTokenPublic:
    return ApiTokenPublic(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
    )


@router.post(
    "/me/tokens",
    response_model=CreateApiTokenResponse,
    status_code=201,
)
async def create_token_endpoint(
    body: CreateApiTokenRequest,
    user_id: str = Depends(require_verified_user_id),
) -> CreateApiTokenResponse:
    """创建 PAT. 响应里的 token 明文仅此一次可见."""
    try:
        plaintext, token = pat_service.create_token(
            user_id=user_id, name=body.name,
        )
    except pat_service.TokenLimitError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return CreateApiTokenResponse(token=plaintext, item=_to_public(token))


@router.get("/me/tokens", response_model=ApiTokensListResponse)
async def list_tokens_endpoint(
    user_id: str = Depends(require_verified_user_id),
) -> ApiTokensListResponse:
    """我的有效 PAT 列表 (不含已撤销; 永不返回 hash / 明文)."""
    items = pat_service.list_tokens(user_id)
    return ApiTokensListResponse(items=[_to_public(t) for t in items])


@router.delete("/me/tokens/{token_id}", status_code=204)
async def revoke_token_endpoint(
    token_id: str,
    user_id: str = Depends(require_verified_user_id),
) -> None:
    """撤销 PAT. 不存在 / 非本人 / 已撤销 → 404 (不区分)."""
    ok = pat_service.revoke_token(user_id=user_id, token_id=token_id)
    if not ok:
        raise HTTPException(404, detail="Token not found")
    return None
