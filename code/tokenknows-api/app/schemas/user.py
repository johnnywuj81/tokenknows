"""User account schema · v1.1.0 T74.

替换 v0.9 X-User-Id trust-on-faith 为真实账户系统:
- 密码 bcrypt hash (passlib)
- JWT access token (sub=user_id, exp=24h default)
- backward-compat: 老 client 仍可传 X-User-Id (但生产应禁用)

MVP:
- 邮箱 + 密码 注册 / 登录
- 不做邮箱验证 (v1.2 加)
- 不做 refresh token (v1.2 加)
- 不做角色 / RBAC (按 project_members 走)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """账户 entity."""

    id: str
    """user-{uuid} 12 hex; 同时作为 platform user_id 在 project_members 引用."""

    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=80)
    password_hash: str
    """bcrypt hash (passlib.hash.bcrypt)."""

    is_instance_admin: bool = False
    """实例管理员 (绕过 project ACL)."""

    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


# ─── 请求 / 响应 DTO ──────────────────────────────────────────────


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=80)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserPublic(BaseModel):
    """对外不暴露 password_hash."""

    id: str
    email: EmailStr
    display_name: str
    is_instance_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AuthTokenResponse(BaseModel):
    """登录 / 注册成功响应."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    """秒数."""
    user: UserPublic
