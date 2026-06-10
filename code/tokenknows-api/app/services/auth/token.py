"""JWT issue / verify · v1.1.0 T74.

MVP HS256 (对称); 生产可换 RS256 + KMS-managed private key.
sub=user_id, exp=now+24h (configurable via JWT_ACCESS_TOKEN_TTL_MINUTES).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.logging import logger
from app.config.settings import get_settings

# bcrypt 全局 context
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthError(Exception):
    """JWT 无效 / 过期 / 密码错误."""


# ─── 密码 hash ───────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """bcrypt hash; 调用方传明文."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """对比 bcrypt hash."""
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        # bcrypt 长度限制等异常 → False
        return False


# ─── JWT issue / decode ──────────────────────────────────────────


def issue_access_token(user_id: str, *, extra_claims: dict | None = None) -> str:
    """签发 access_token. sub=user_id, exp=now+TTL."""
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.jwt_access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return token


def decode_token(token: str) -> dict[str, Any]:
    """验证并解出 payload; 失败抛 AuthError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        logger.debug("jwt_decode_failed", error=str(e))
        raise AuthError(f"invalid token: {e}") from e
    if payload.get("type") != "access":
        raise AuthError("not an access token")
    if not payload.get("sub"):
        raise AuthError("token missing sub claim")
    return payload


def get_user_id_from_token(token: str) -> str:
    """从 token 取 sub (user_id); 失败抛 AuthError."""
    payload = decode_token(token)
    return payload["sub"]


__all__ = [
    "AuthError",
    "decode_token",
    "get_user_id_from_token",
    "hash_password",
    "issue_access_token",
    "verify_password",
]
