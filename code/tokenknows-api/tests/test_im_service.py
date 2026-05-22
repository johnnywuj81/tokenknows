"""im_service · IM 连接生命周期 (v0.3 T18).

覆盖:
- create_connection: 默认 pending + 内存 + SQLite 双写
- get_connection / list_connections (project 隔离, status 过滤)
- delete_connection 级联
- update_status (revoked 自动填 revoked_at)
- apply_oauth_result 加密 token + 切 active
- build_connector 通过 registry 找 class + 解密 token
- bootstrap 从 SQLite 还原
- Fernet 加密失败时不写脏数据
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import settings as settings_module
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im.connector_base import (
    ConnectorError,
    IMConnector,
    OAuthExchangeResult,
    registry,
)
from app.services.im.feishu_connector import FeishuConnector


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    # 一个真实可用的 Fernet 主密钥
    settings_module.get_settings().im_encryption_key = Fernet.generate_key().decode()
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── CRUD ───────────────────────────────────────────────────


def test_create_connection_pending(fresh_state) -> None:
    conn = im_service.create_connection("p1", "feishu", consent_signed_by="admin")
    assert conn.status == "pending"
    assert conn.platform == "feishu"
    assert conn.consent_signed_by == "admin"
    # cache + DB 都写了
    assert im_service.get_connection(conn.id) is conn
    assert len(fresh_state.list_im_connections("p1")) == 1


def test_list_connections_filter_status() -> None:
    c1 = im_service.create_connection("p1", "feishu")
    c2 = im_service.create_connection("p1", "dingtalk")
    im_service.update_status(c2.id, "active")
    actives = im_service.list_connections("p1", status="active")
    assert [c.id for c in actives] == [c2.id]


def test_list_connections_isolated_by_project() -> None:
    a = im_service.create_connection("proj-A", "feishu")
    b = im_service.create_connection("proj-B", "feishu")
    assert [c.id for c in im_service.list_connections("proj-A")] == [a.id]
    assert [c.id for c in im_service.list_connections("proj-B")] == [b.id]


def test_get_connection_missing_returns_none() -> None:
    assert im_service.get_connection("ghost") is None


def test_delete_connection_removes_from_cache_and_db(fresh_state) -> None:
    c = im_service.create_connection("p1", "feishu")
    assert im_service.delete_connection(c.id) is True
    assert im_service.get_connection(c.id) is None
    assert fresh_state.list_im_connections("p1") == []


def test_delete_connection_missing_returns_false() -> None:
    assert im_service.delete_connection("ghost") is False


def test_update_status_revoked_stamps_revoked_at() -> None:
    c = im_service.create_connection("p1", "feishu")
    updated = im_service.update_status(c.id, "revoked")
    assert updated is not None
    assert updated.status == "revoked"
    assert updated.revoked_at is not None


def test_update_status_active_does_not_set_revoked_at() -> None:
    c = im_service.create_connection("p1", "feishu")
    updated = im_service.update_status(c.id, "active")
    assert updated is not None
    assert updated.revoked_at is None


def test_update_status_missing_returns_none() -> None:
    assert im_service.update_status("ghost", "active") is None


# ─── apply_oauth_result ─────────────────────────────────────


def test_apply_oauth_result_encrypts_tokens_and_activates() -> None:
    c = im_service.create_connection("p1", "feishu")
    result = OAuthExchangeResult(
        access_token="user-access-123",
        refresh_token="user-refresh-456",
        expires_at=_now() + timedelta(hours=2),
        tenant_name="My Corp",
        user_id="open-id-001",
    )
    updated = im_service.apply_oauth_result(c.id, result)
    assert updated is not None
    assert updated.status == "active"
    assert updated.tenant_name == "My Corp"
    assert updated.auth_token_enc is not None
    assert updated.refresh_token_enc is not None
    # 密文不等于明文
    assert updated.auth_token_enc != "user-access-123"
    # 但可解密回去
    assert im_crypto.decrypt_token(updated.auth_token_enc) == "user-access-123"
    assert im_crypto.decrypt_token(updated.refresh_token_enc) == "user-refresh-456"


def test_apply_oauth_result_keeps_consent_signed_at() -> None:
    c = im_service.create_connection("p1", "feishu")
    # 先有 consent_signed_at 设过的
    pre = _now() - timedelta(days=1)
    c2 = c.model_copy(update={"consent_signed_at": pre})
    im_service.get_registry().upsert(c2)
    updated = im_service.apply_oauth_result(c.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
    ))
    assert updated is not None
    assert updated.consent_signed_at == pre


def test_apply_oauth_result_missing_connection_returns_none() -> None:
    assert im_service.apply_oauth_result("ghost", OAuthExchangeResult(
        access_token="x", refresh_token=None, expires_at=None,
    )) is None


# ─── build_connector ────────────────────────────────────────


def test_build_connector_returns_feishu_instance() -> None:
    c = im_service.create_connection("p1", "feishu")
    inst = im_service.build_connector(c)
    assert isinstance(inst, FeishuConnector)


def test_build_connector_decrypts_tokens() -> None:
    c = im_service.create_connection("p1", "feishu")
    updated = im_service.apply_oauth_result(c.id, OAuthExchangeResult(
        access_token="my-secret-token",
        refresh_token=None,
        expires_at=None,
    ))
    inst = im_service.build_connector(updated)
    assert inst._access_token == "my-secret-token"


def test_build_connector_handles_decrypt_failure_gracefully(monkeypatch) -> None:
    """密文损坏时 connector 仍构造成功, access_token=None."""
    c = im_service.create_connection("p1", "feishu")
    # 注入损坏的密文
    corrupted = c.model_copy(update={"auth_token_enc": "deadbeef-invalid"})
    im_service.get_registry().upsert(corrupted)
    inst = im_service.build_connector(corrupted)
    assert inst._access_token is None


def test_build_connector_unknown_platform_raises(monkeypatch) -> None:
    """未注册 platform → ConnectorError."""
    c = im_service.create_connection("p1", "feishu")
    # 临时清掉飞书注册
    backup_cls = registry.get("feishu")
    registry.clear()
    try:
        with pytest.raises(ConnectorError, match="未注册"):
            im_service.build_connector(c)
    finally:
        if backup_cls is not None:
            registry.register("feishu", backup_cls)


# ─── bootstrap ──────────────────────────────────────────────


def test_bootstrap_restores_connections_from_db(fresh_state) -> None:
    c = im_service.create_connection("p1", "feishu")
    # 模拟应用重启
    im_service.reset_registry_for_tests()
    im_service.bootstrap()
    loaded = im_service.get_connection(c.id)
    assert loaded is not None
    assert loaded.platform == "feishu"


def test_bootstrap_is_idempotent(fresh_state) -> None:
    im_service.create_connection("p1", "feishu")
    im_service.bootstrap()
    im_service.bootstrap()  # 二次调用不重复加载
    assert len(im_service.list_connections("p1")) == 1
