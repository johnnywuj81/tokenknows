"""同意书签字 + 钉钉/企微 connector (v0.3.1 J + K).

J 覆盖:
- POST /im/connections/:id/consent body=accepts_terms=true → 写 consent_signed_*
- 404 if connection 不存在
- 400 if accepts_terms=false
- 二次 sign 覆盖 consent_signed_by (更新 not delete)

K 覆盖:
- registry.get("dingtalk") / registry.get("wework") 返 class
- DingTalkConnector / WeworkConnector authorize_url 含 placeholder + 不报错
- exchange_code / refresh_token / list_chats 抛 NotImplementedError (或 ConnectorError)
- health 返 ok=False + note 提示
- revoke 清本地 token
- POST /projects/:id/im/connections platform=dingtalk → 创建 + 返 authorize_url
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im import dingtalk_connector, wework_connector  # noqa
from app.services.im.connector_base import (
    OAuthExchangeError,
    TokenExpiredError,
    registry,
)
from app.services.im.dingtalk_connector import DingTalkConnector
from app.services.im.wework_connector import WeworkConnector


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    s = settings_module.get_settings()
    s.im_encryption_key = Fernet.generate_key().decode()
    s.feishu_app_id = "cli"
    s.feishu_app_secret = "x"
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ─── J · 同意书签字 ─────────────────────────────────────────


def test_consent_404_when_connection_missing(client: TestClient) -> None:
    r = client.post(
        "/api/v1/im/connections/ghost/consent",
        json={"signed_by": "admin-1", "accepts_terms": True},
    )
    assert r.status_code == 404


def test_consent_400_when_not_accepted(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    r = client.post(
        f"/api/v1/im/connections/{conn.id}/consent",
        json={"signed_by": "admin-1", "accepts_terms": False},
    )
    assert r.status_code == 400


def test_consent_records_signed_by(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    r = client.post(
        f"/api/v1/im/connections/{conn.id}/consent",
        json={
            "signed_by": "admin-1",
            "user_id": "emp-007",
            "accepts_terms": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["consent_signed_by"] == "admin-1"
    assert data["consent_user_id"] == "emp-007"
    assert data["consent_signed_at"] is not None


def test_consent_resigning_updates_record(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    r1 = client.post(
        f"/api/v1/im/connections/{conn.id}/consent",
        json={"signed_by": "admin-A", "accepts_terms": True},
    )
    first_signed_at = r1.json()["consent_signed_at"]

    r2 = client.post(
        f"/api/v1/im/connections/{conn.id}/consent",
        json={"signed_by": "admin-B", "accepts_terms": True},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["consent_signed_by"] == "admin-B"
    # consent_signed_at 应更新
    assert data["consent_signed_at"] != first_signed_at


def test_consent_requires_terms_field(client: TestClient) -> None:
    conn = im_service.create_connection("p1", "feishu")
    r = client.post(
        f"/api/v1/im/connections/{conn.id}/consent",
        json={"signed_by": "x"},  # 缺 accepts_terms
    )
    assert r.status_code == 422


# ─── K · Registry 注册 ─────────────────────────────────────


def test_registry_has_all_4_platforms() -> None:
    assert registry.get("feishu") is not None
    assert registry.get("dingtalk") is DingTalkConnector
    assert registry.get("wework") is WeworkConnector
    # 不在范围: email 没注册 connector (设计上不接)
    assert registry.get("email") is None


# ─── K · DingTalkConnector ─────────────────────────────────


@pytest.mark.asyncio
async def test_dingtalk_authorize_url_returns_placeholder() -> None:
    conn = DingTalkConnector()
    url = await conn.get_authorize_url("p1", "http://x/cb", "state-1")
    assert "login.dingtalk.com" in url
    assert "state=state-1" in url
    assert "#dingtalk-not-configured" in url


@pytest.mark.asyncio
async def test_dingtalk_exchange_code_raises() -> None:
    conn = DingTalkConnector()
    with pytest.raises(OAuthExchangeError, match="v0.4"):
        await conn.exchange_code("any-code")


@pytest.mark.asyncio
async def test_dingtalk_refresh_token_raises_expired() -> None:
    conn = DingTalkConnector()
    with pytest.raises(TokenExpiredError):
        await conn.refresh_token("any")


@pytest.mark.asyncio
async def test_dingtalk_messaging_methods_not_implemented() -> None:
    conn = DingTalkConnector()
    with pytest.raises(NotImplementedError):
        await conn.list_chats()
    with pytest.raises(NotImplementedError):
        await conn.add_bot_to_chat("ch")
    with pytest.raises(NotImplementedError):
        await conn.list_chat_members("ch")


@pytest.mark.asyncio
async def test_dingtalk_revoke_clears_local() -> None:
    conn = DingTalkConnector(access_token="a", refresh_token="b")
    await conn.revoke()
    assert conn._access_token is None
    assert conn._refresh_token is None


@pytest.mark.asyncio
async def test_dingtalk_health_warn() -> None:
    h = await DingTalkConnector().health()
    assert h.ok is False
    assert "v0.4" in h.note


# ─── K · WeworkConnector ───────────────────────────────────


@pytest.mark.asyncio
async def test_wework_authorize_url() -> None:
    conn = WeworkConnector()
    url = await conn.get_authorize_url("p1", "http://x/cb", "state-y")
    assert "open.work.weixin.qq.com" in url
    assert "state=state-y" in url
    assert "#wework-not-configured" in url


@pytest.mark.asyncio
async def test_wework_exchange_raises() -> None:
    with pytest.raises(OAuthExchangeError):
        await WeworkConnector().exchange_code("x")


@pytest.mark.asyncio
async def test_wework_health() -> None:
    h = await WeworkConnector().health()
    assert h.ok is False


# ─── K · 通过 HTTP 创建钉钉/企微 connection ─────────────────


def test_http_create_dingtalk_returns_placeholder_url(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/v1/projects/p1/im/connections",
        json={"platform": "dingtalk"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["connection"]["platform"] == "dingtalk"
    assert "login.dingtalk.com" in data["authorize_url"]


def test_http_create_wework_returns_placeholder_url(
    client: TestClient,
) -> None:
    r = client.post(
        "/api/v1/projects/p1/im/connections",
        json={"platform": "wework"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["connection"]["platform"] == "wework"
    assert "open.work.weixin.qq.com" in data["authorize_url"]


def test_im_service_build_connector_dingtalk() -> None:
    conn = im_service.create_connection("p1", "dingtalk")
    instance = im_service.build_connector(conn)
    assert isinstance(instance, DingTalkConnector)


def test_im_service_build_connector_wework() -> None:
    conn = im_service.create_connection("p1", "wework")
    instance = im_service.build_connector(conn)
    assert isinstance(instance, WeworkConnector)
