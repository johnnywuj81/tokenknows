"""User CRUD + register/login · v1.1.0 T74."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.config.logging import logger
from app.persistence import store as store_module
from app.schemas.user import User
from app.services.auth.token import hash_password, verify_password


class UserAlreadyExists(Exception):
    """email 已注册."""


class InvalidCredentials(Exception):
    """登录失败 (用户不存在 / 密码错)."""


def register(
    *,
    email: str,
    password: str,
    display_name: str,
    is_instance_admin: bool = False,
    now: datetime | None = None,
) -> User:
    """注册新账户.

    Raises:
        UserAlreadyExists: email 已注册.
    """
    db = store_module.get_db()
    normalized_email = email.strip().lower()
    if db.get_user_by_email(normalized_email):
        raise UserAlreadyExists(f"email already registered: {normalized_email}")
    now_utc = now or datetime.now(timezone.utc)
    user = User(
        id=f"user-{uuid.uuid4().hex[:12]}",
        email=normalized_email,
        display_name=display_name,
        password_hash=hash_password(password),
        is_instance_admin=is_instance_admin,
        created_at=now_utc,
        updated_at=now_utc,
        last_login_at=None,
    )
    db.upsert_user(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        password_hash=user.password_hash,
        is_instance_admin=user.is_instance_admin,
        last_login_at=None,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        json_str=user.model_dump_json(),
    )
    logger.info("user_registered", user_id=user.id, email=user.email)
    return user


def login(*, email: str, password: str) -> User:
    """验证 email + 密码; 成功返回 User (并更新 last_login_at).

    Raises:
        InvalidCredentials: 用户不存在 / 密码错.
    """
    db = store_module.get_db()
    normalized_email = email.strip().lower()
    raw = db.get_user_by_email(normalized_email)
    if raw is None:
        # 同样消息避免 enumeration attack
        raise InvalidCredentials("invalid email or password")
    user = User.model_validate(raw)
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("invalid email or password")
    # 更新 last_login_at
    now = datetime.now(timezone.utc)
    updated = user.model_copy(update={
        "last_login_at": now,
        "updated_at": now,
    })
    db.upsert_user(
        user_id=updated.id,
        email=updated.email,
        display_name=updated.display_name,
        password_hash=updated.password_hash,
        is_instance_admin=updated.is_instance_admin,
        last_login_at=now.isoformat(),
        created_at=updated.created_at.isoformat(),
        updated_at=now.isoformat(),
        json_str=updated.model_dump_json(),
    )
    logger.info("user_logged_in", user_id=updated.id)
    return updated


def get_user(user_id: str) -> User | None:
    db = store_module.get_db()
    raw = db.get_user_by_id(user_id)
    if raw is None:
        return None
    return User.model_validate(raw)


__all__ = [
    "InvalidCredentials",
    "UserAlreadyExists",
    "get_user",
    "login",
    "register",
]
