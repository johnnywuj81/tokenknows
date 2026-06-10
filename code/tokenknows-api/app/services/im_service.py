"""IM 连接生命周期管理 (v0.3 T18+).

职责:
- 创建/查询/更新/删除 IMConnection (内存 cache + SQLite 持久化)
- access_token / refresh_token 透明加解密 (im_crypto)
- 通过 ConnectorRegistry 构造对应 platform connector 实例
- 把 OAuth 兑换结果写回 IMConnection

不在范围:
- 实际 OAuth URL 生成 / 兑换 (FeishuConnector.exchange_code 等)
- 消息拉取 (T19)
- ValueSegment 组装 (T21)
- Retention 清理 (T22)
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.im import (
    IMConnection,
    IMConnectionStatus,
    IMPlatform,
)
from app.services.im import (  # noqa: F401 注册副作用
    dingtalk_connector,
    feishu_connector,
    wework_connector,
)
from app.services.im.connector_base import (
    ConnectorError,
    IMConnector,
    OAuthExchangeResult,
    registry,
)
from app.services.im_crypto import TokenCryptoError, decrypt_token, encrypt_token


class _IMRegistry:
    """单进程内存 cache (cache-aside)."""

    def __init__(self) -> None:
        self._cache: dict[str, IMConnection] = {}
        self._by_project: dict[str, set[str]] = {}
        self._lock = threading.RLock()
        self._bootstrapped = False

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        rows = get_db().load_all_im_connections()
        for row in rows:
            try:
                conn = IMConnection.model_validate(row)
            except Exception as e:
                logger.warning("im_connection_parse_failed", id=row.get("id"), error=str(e))
                continue
            self._cache[conn.id] = conn
            self._by_project.setdefault(conn.project_id, set()).add(conn.id)
        self._bootstrapped = True
        logger.info("im_connections_bootstrapped", count=len(self._cache))

    def get(self, connection_id: str) -> IMConnection | None:
        return self._cache.get(connection_id)

    def list_for_project(
        self, project_id: str, status: IMConnectionStatus | None = None
    ) -> list[IMConnection]:
        ids = self._by_project.get(project_id, set())
        out = [self._cache[i] for i in ids if i in self._cache]
        if status:
            out = [c for c in out if c.status == status]
        out.sort(key=lambda c: c.updated_at, reverse=True)
        return out

    def upsert(self, conn: IMConnection) -> None:
        with self._lock:
            self._cache[conn.id] = conn
            self._by_project.setdefault(conn.project_id, set()).add(conn.id)
            self._persist(conn)

    def delete(self, connection_id: str) -> bool:
        with self._lock:
            existing = self._cache.pop(connection_id, None)
            if existing is None:
                return False
            self._by_project.get(existing.project_id, set()).discard(connection_id)
            get_db().delete_im_connection(connection_id)
            return True

    def _persist(self, conn: IMConnection) -> None:
        get_db().upsert_im_connection(
            connection_id=conn.id,
            project_id=conn.project_id,
            platform=conn.platform,
            status=conn.status,
            updated_at=conn.updated_at.isoformat(),
            json_str=conn.model_dump_json(),
        )


_registry = _IMRegistry()


def bootstrap() -> None:
    """供 main.py lifespan 调."""
    _registry.bootstrap()


def get_registry() -> _IMRegistry:
    return _registry


# ─── CRUD ────────────────────────────────────────────────


def create_connection(
    project_id: str,
    platform: IMPlatform,
    consent_signed_by: str | None = None,
    consent_user_id: str | None = None,
) -> IMConnection:
    """新建 pending 状态的 IMConnection. OAuth 完成前 token 字段为空."""
    now = datetime.now(UTC)
    conn = IMConnection(
        id=f"im-{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        platform=platform,
        consent_signed_by=consent_signed_by,
        consent_user_id=consent_user_id,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    _registry.upsert(conn)
    logger.info("im_connection_created", id=conn.id, project=project_id, platform=platform)
    return conn


def get_connection(connection_id: str) -> IMConnection | None:
    return _registry.get(connection_id)


def list_connections(
    project_id: str, status: IMConnectionStatus | None = None
) -> list[IMConnection]:
    return _registry.list_for_project(project_id, status)


def delete_connection(connection_id: str) -> bool:
    return _registry.delete(connection_id)


def update_status(
    connection_id: str, status: IMConnectionStatus
) -> IMConnection | None:
    conn = _registry.get(connection_id)
    if conn is None:
        return None
    updated = conn.model_copy(update={
        "status": status,
        "updated_at": datetime.now(UTC),
        "revoked_at": (
            datetime.now(UTC) if status == "revoked" else conn.revoked_at
        ),
    })
    _registry.upsert(updated)
    logger.info("im_connection_status_changed", id=connection_id, status=status)
    return updated


def apply_oauth_result(
    connection_id: str, result: OAuthExchangeResult
) -> IMConnection | None:
    """OAuth 成功回调: 加密 token + 写 IMConnection + 切 active."""
    conn = _registry.get(connection_id)
    if conn is None:
        return None
    try:
        access_enc = encrypt_token(result.access_token) if result.access_token else None
        refresh_enc = (
            encrypt_token(result.refresh_token) if result.refresh_token else None
        )
    except TokenCryptoError as e:
        logger.error("im_oauth_encrypt_failed", id=connection_id, error=str(e))
        raise
    now = datetime.now(UTC)
    updated = conn.model_copy(update={
        "auth_token_enc": access_enc,
        "refresh_token_enc": refresh_enc,
        "token_expires_at": result.expires_at,
        "tenant_name": result.tenant_name or conn.tenant_name,
        "status": "active",
        "consent_signed_at": conn.consent_signed_at or now,
        "updated_at": now,
    })
    _registry.upsert(updated)
    logger.info(
        "im_oauth_applied",
        id=connection_id,
        platform=conn.platform,
        tenant=updated.tenant_name,
    )
    return updated


# ─── Connector 工厂 ──────────────────────────────────────────


def build_connector(connection: IMConnection) -> IMConnector:
    """根据 connection.platform 找 connector class, 注入解密 token, 返回实例."""
    cls = registry.get(connection.platform)
    if cls is None:
        raise ConnectorError(f"未注册的 platform: {connection.platform}")
    access = None
    refresh = None
    try:
        if connection.auth_token_enc:
            access = decrypt_token(connection.auth_token_enc)
        if connection.refresh_token_enc:
            refresh = decrypt_token(connection.refresh_token_enc)
    except TokenCryptoError as e:
        logger.warning(
            "im_connector_token_decrypt_failed",
            id=connection.id,
            error=str(e),
        )
        access = None
        refresh = None
    # 各 connector 都接受 (access_token, refresh_token) 二参
    return cls(access_token=access, refresh_token=refresh)


def reset_registry_for_tests() -> None:
    """测试用."""
    global _registry
    _registry = _IMRegistry()
