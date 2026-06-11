"""Personal Access Token CRUD + verify · v2.1.

明文格式: `tkk_<secrets.token_urlsafe(32)>`; DB 只存 sha256 hash.
verify 为 auth 热路径 (每个 MCP 请求都走), last_used_at 写入做 60s 节流.
纯 stdlib (hashlib / secrets / uuid), 不依赖 passlib.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from app.config.logging import logger
from app.persistence import store as store_module
from app.schemas.api_token import ApiToken

TOKEN_PREFIX = "tkk_"

# last_used_at 写节流窗口 (秒): 距上次写 < 此值则跳过, 避免每请求一次 UPDATE
_LAST_USED_THROTTLE_SECONDS = 60

# 单 user 有效 PAT 上限: 防滥发 (误用脚本狂建 / 命名空间塞爆)
MAX_ACTIVE_TOKENS_PER_USER = 20


class TokenLimitError(ValueError):
    """有效 token 数已达上限."""


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_token(
    *,
    user_id: str,
    name: str,
    now: datetime | None = None,
) -> tuple[str, ApiToken]:
    """签发新 PAT. 返回 (明文, ApiToken).

    明文仅此一次可见; DB 只落 sha256 hash + 前 12 字符 prefix.
    """
    db_check = store_module.get_db()
    if len(db_check.list_api_tokens_for_user(user_id)) >= MAX_ACTIVE_TOKENS_PER_USER:
        raise TokenLimitError(
            f"active token limit reached ({MAX_ACTIVE_TOKENS_PER_USER}); "
            "revoke unused tokens first"
        )
    plaintext = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    now_utc = now or datetime.now(UTC)
    token = ApiToken(
        id=f"pat-{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        name=name,
        token_hash=_hash_token(plaintext),
        token_prefix=plaintext[:12],
        created_at=now_utc,
        last_used_at=None,
        revoked_at=None,
    )
    db = store_module.get_db()
    db.insert_api_token(
        token_id=token.id,
        user_id=token.user_id,
        name=token.name,
        token_hash=token.token_hash,
        token_prefix=token.token_prefix,
        created_at=token.created_at.isoformat(),
        json_str=token.model_dump_json(),
    )
    logger.info("api_token_created", token_id=token.id, user_id=user_id)
    return plaintext, token


def list_tokens(user_id: str) -> list[ApiToken]:
    """某 user 的有效 PAT 列表 (新建在前, 不含已撤销)."""
    db = store_module.get_db()
    return [
        ApiToken.model_validate(raw)
        for raw in db.list_api_tokens_for_user(user_id)
    ]


def revoke_token(*, user_id: str, token_id: str) -> bool:
    """撤销 PAT. 仅 owner 可撤; 不存在 / 非本人 / 已撤销 → False."""
    db = store_module.get_db()
    raw = None
    for candidate in db.list_api_tokens_for_user(user_id):
        if candidate.get("id") == token_id:
            raw = candidate
            break
    if raw is None:
        return False
    now = datetime.now(UTC)
    token = ApiToken.model_validate(raw)
    revoked = token.model_copy(update={"revoked_at": now})
    ok = db.revoke_api_token(
        token_id=token_id,
        user_id=user_id,
        revoked_at_iso=now.isoformat(),
        json_str=revoked.model_dump_json(),
    )
    if ok:
        logger.info("api_token_revoked", token_id=token_id, user_id=user_id)
    return ok


def verify_token(plaintext: str) -> str | None:
    """验证 PAT 明文 → user_id; 无效 / 已撤销 → None.

    热路径: prefix 短路 → sha256 → 单行索引查询.
    命中时节流更新 last_used_at (None 或距上次 > 60s 才写).
    """
    if not plaintext or not plaintext.startswith(TOKEN_PREFIX):
        return None
    db = store_module.get_db()
    raw = db.get_api_token_by_hash(_hash_token(plaintext))
    if raw is None:
        return None
    token = ApiToken.model_validate(raw)
    # 纵深防御: SQL 已过滤 revoked, 这里再挡一道 (防未来查询改动漏放)
    if token.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    should_touch = (
        token.last_used_at is None
        or (now - token.last_used_at).total_seconds() > _LAST_USED_THROTTLE_SECONDS
    )
    if should_touch:
        touched = token.model_copy(update={"last_used_at": now})
        db.touch_api_token_last_used(
            token_id=token.id,
            last_used_iso=now.isoformat(),
            json_str=touched.model_dump_json(),
        )
    return token.user_id


__all__ = [
    "MAX_ACTIVE_TOKENS_PER_USER",
    "TOKEN_PREFIX",
    "TokenLimitError",
    "create_token",
    "list_tokens",
    "revoke_token",
    "verify_token",
]
