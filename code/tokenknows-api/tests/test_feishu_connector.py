"""FeishuConnector OAuth 4 方法 (v0.3 T18).

覆盖:
- get_authorize_url 拼参 + scope
- exchange_code 失败 (app 凭据未配置 / 飞书返 非 0 code / HTTP 错误)
- exchange_code 成功 → OAuthExchangeResult
- refresh_token 成功 / refresh_token 空 / 飞书拒绝 → TokenExpiredError
- revoke 清本地 token
- health 凭据齐 → ok=True; 凭据缺 → ok=False
- T19 占位方法 NotImplementedError
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings as settings_module
from app.services.im.connector_base import (
    OAuthExchangeError,
    TokenExpiredError,
)
from app.services.im.feishu_connector import FeishuConnector


@pytest.fixture
def with_app_creds(monkeypatch: pytest.MonkeyPatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "feishu_app_id", "cli_test123")
    monkeypatch.setattr(s, "feishu_app_secret", "secret-xyz")
    yield


@pytest.fixture
def no_app_creds(monkeypatch: pytest.MonkeyPatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "feishu_app_id", None)
    monkeypatch.setattr(s, "feishu_app_secret", None)
    yield


# ─── get_authorize_url ──────────────────────────────────────


@pytest.mark.asyncio
async def test_authorize_url_contains_scopes(with_app_creds) -> None:
    conn = FeishuConnector()
    url = await conn.get_authorize_url(
        project_id="p1",
        redirect_uri="http://localhost:8001/cb",
        state="conn-001",
    )
    assert "/open-apis/authen/v1/authorize" in url
    assert "app_id=cli_test123" in url
    assert "state=conn-001" in url
    assert "scope=" in url
    assert "im%3Amessage" in url  # URL-encoded


@pytest.mark.asyncio
async def test_authorize_url_missing_creds_raises(no_app_creds) -> None:
    conn = FeishuConnector()
    with pytest.raises(OAuthExchangeError, match="FEISHU_APP_ID"):
        await conn.get_authorize_url("p1", "http://x", "s1")


# ─── exchange_code ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_success(with_app_creds) -> None:
    """先返 app_access_token, 再返 user access_token."""
    call_count = {"i": 0}

    async def fake_post(url, json=None, headers=None):
        call_count["i"] += 1
        if call_count["i"] == 1:  # app_access_token
            payload = {"code": 0, "app_access_token": "app-token"}
        else:  # exchange
            payload = {
                "code": 0,
                "data": {
                    "access_token": "user-access",
                    "refresh_token": "user-refresh",
                    "expires_in": 7200,
                    "tenant_key": "tenant-xyz",
                    "open_id": "ou-001",
                },
            }
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        result = await conn.exchange_code(code="oauth-code-1")
    assert result.access_token == "user-access"
    assert result.refresh_token == "user-refresh"
    assert result.tenant_name == "tenant-xyz"
    assert result.user_id == "ou-001"
    assert result.expires_at is not None
    assert result.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_exchange_code_non_zero_code_raises(with_app_creds) -> None:
    """飞书返 code=400 → OAuthExchangeError."""

    async def fake_post(url, json=None, headers=None):
        return httpx.Response(
            200,
            json={"code": 0, "app_access_token": "x"}
            if "app_access_token" in url
            else {"code": 99991663, "msg": "code expired"},
            request=httpx.Request("POST", url),
        )

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        with pytest.raises(OAuthExchangeError, match="99991663"):
            await conn.exchange_code(code="bad")


@pytest.mark.asyncio
async def test_exchange_code_http_error_raises(with_app_creds) -> None:
    """飞书 5xx → OAuthExchangeError."""

    async def fake_post(url, json=None, headers=None):
        if "app_access_token" in url:
            return httpx.Response(
                200, json={"code": 0, "app_access_token": "x"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            500, text="server error",
            request=httpx.Request("POST", url),
        )

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        with pytest.raises(OAuthExchangeError, match="HTTP 500"):
            await conn.exchange_code(code="x")


@pytest.mark.asyncio
async def test_exchange_code_missing_access_token_field(with_app_creds) -> None:
    async def fake_post(url, json=None, headers=None):
        if "app_access_token" in url:
            return httpx.Response(
                200, json={"code": 0, "app_access_token": "x"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200, json={"code": 0, "data": {}},
            request=httpx.Request("POST", url),
        )

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        with pytest.raises(OAuthExchangeError, match="access_token"):
            await conn.exchange_code(code="x")


# ─── refresh_token ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_success(with_app_creds) -> None:
    async def fake_post(url, json=None, headers=None):
        if "app_access_token" in url:
            payload = {"code": 0, "app_access_token": "app-token"}
        else:
            payload = {
                "code": 0,
                "data": {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 7200,
                },
            }
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        result = await conn.refresh_token("old-refresh")
    assert result.access_token == "new-access"


@pytest.mark.asyncio
async def test_refresh_token_empty_raises_token_expired(with_app_creds) -> None:
    conn = FeishuConnector()
    with pytest.raises(TokenExpiredError, match="refresh_token 为空"):
        await conn.refresh_token("")


@pytest.mark.asyncio
async def test_refresh_token_provider_error_raises_token_expired(with_app_creds) -> None:
    async def fake_post(url, json=None, headers=None):
        if "app_access_token" in url:
            return httpx.Response(
                200, json={"code": 0, "app_access_token": "x"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={"code": 99991671, "msg": "refresh_token invalid"},
            request=httpx.Request("POST", url),
        )

    conn = FeishuConnector()
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        with pytest.raises(TokenExpiredError):
            await conn.refresh_token("old")


# ─── revoke / health / T19 占位 ─────────────────────────────


@pytest.mark.asyncio
async def test_revoke_clears_local_tokens() -> None:
    conn = FeishuConnector(access_token="a", refresh_token="b")
    await conn.revoke()
    assert conn._access_token is None
    assert conn._refresh_token is None


@pytest.mark.asyncio
async def test_health_ok_when_creds_set(with_app_creds) -> None:
    h = await FeishuConnector().health()
    assert h.ok is True
    assert h.note is None


@pytest.mark.asyncio
async def test_health_warn_when_creds_missing(no_app_creds) -> None:
    h = await FeishuConnector().health()
    assert h.ok is False
    assert h.note is not None and "FEISHU_APP_ID" in h.note


@pytest.mark.asyncio
async def test_t19_methods_require_access_token() -> None:
    """T19 已实施, 缺 token → TokenExpiredError."""
    conn = FeishuConnector(access_token=None)
    with pytest.raises(TokenExpiredError):
        await conn.list_chats()
    with pytest.raises(TokenExpiredError):
        await conn.add_bot_to_chat("chat-1")
    with pytest.raises(TokenExpiredError):
        await conn.list_chat_members("chat-1")
