"""IM OAuth callback HTTP integration (v0.3 T18).

覆盖:
- GET /api/v1/webhooks/feishu/auth-callback 成功
- 404 if connection 不存在
- 400 if connection.platform != feishu
- 400 if 飞书 OAuth 兑换失败 → connection 标 revoked
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im.connector_base import (
    OAuthExchangeError,
    OAuthExchangeResult,
)
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    settings_module.get_settings().im_encryption_key = Fernet.generate_key().decode()
    im_crypto.reset_fernet_cache()
    yield
    im_crypto.reset_fernet_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_callback_404_when_connection_missing(client: TestClient) -> None:
    r = client.get("/api/v1/webhooks/feishu/auth-callback?code=abc&state=ghost")
    assert r.status_code == 404


def test_callback_400_when_wrong_platform(client: TestClient) -> None:
    """Connection.platform != feishu 时拒绝."""
    conn = im_service.create_connection("p1", "dingtalk")
    r = client.get(
        f"/api/v1/webhooks/feishu/auth-callback?code=abc&state={conn.id}"
    )
    assert r.status_code == 400


def test_callback_happy_path(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    mock_result = OAuthExchangeResult(
        access_token="user-access",
        refresh_token="user-refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        tenant_name="MyCorp",
        user_id="ou-001",
    )
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.exchange_code",
        new=AsyncMock(return_value=mock_result),
    ):
        r = client.get(
            f"/api/v1/webhooks/feishu/auth-callback?code=abc&state={conn.id}"
        )
    assert r.status_code == 200
    data = r.json()
    assert data["connection_id"] == conn.id
    assert data["status"] == "active"
    assert data["tenant_name"] == "MyCorp"

    # 复查 connection 持久化
    refreshed = im_service.get_connection(conn.id)
    assert refreshed is not None
    assert refreshed.status == "active"
    assert refreshed.auth_token_enc is not None
    # 解密能还原
    assert im_crypto.decrypt_token(refreshed.auth_token_enc) == "user-access"


def test_callback_exchange_failure_marks_revoked(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.exchange_code",
        new=AsyncMock(side_effect=OAuthExchangeError("code expired")),
    ):
        r = client.get(
            f"/api/v1/webhooks/feishu/auth-callback?code=bad&state={conn.id}"
        )
    assert r.status_code == 400
    refreshed = im_service.get_connection(conn.id)
    assert refreshed is not None
    assert refreshed.status == "revoked"
