"""HTTP API · v1.1.0 T74 Auth endpoints.

POST /auth/register  - 注册新账户
POST /auth/login     - 验证密码 → access_token
GET  /auth/me        - 当前 session 的 User 资料

MVP: 无邮箱验证, 无 refresh_token (留 v1.2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config.logging import logger
from app.config.settings import get_settings
from app.gateway.http_api._session import require_user_id
from app.schemas.user import (
    AuthTokenResponse,
    User,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services.auth import token as auth_token
from app.services.auth import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_instance_admin=user.is_instance_admin,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=201,
)
async def register_endpoint(body: UserRegisterRequest) -> AuthTokenResponse:
    """注册账户. 成功返 access_token + UserPublic.

    409 if email 已存在.
    """
    try:
        user = user_service.register(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    except user_service.UserAlreadyExists as e:
        raise HTTPException(409, detail=str(e)) from e

    access_token = auth_token.issue_access_token(user.id)
    settings = get_settings()
    return AuthTokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_ttl_minutes * 60,
        user=_to_public(user),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login_endpoint(body: UserLoginRequest) -> AuthTokenResponse:
    """email + password → access_token.

    401 if 凭据错 (用同样 error 防 enumeration).
    """
    try:
        user = user_service.login(email=body.email, password=body.password)
    except user_service.InvalidCredentials:
        raise HTTPException(401, detail="invalid email or password")

    access_token = auth_token.issue_access_token(user.id)
    settings = get_settings()
    return AuthTokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_ttl_minutes * 60,
        user=_to_public(user),
    )


@router.get("/me", response_model=UserPublic)
async def get_me_endpoint(
    user_id: str = Depends(require_user_id),
) -> UserPublic:
    """返回当前 session 的 user 资料. 401 if no session."""
    user = user_service.get_user(user_id)
    if user is None:
        # token 有效但 DB 里没了 (e.g. 删除账户后旧 token 仍能解 sub)
        raise HTTPException(401, detail="user not found")
    return _to_public(user)
