"""IM access_token 自动后台刷新 (v0.3.1 I).

覆盖:
- list_due_connections: 过滤 status/refresh_token/expires_at
- refresh_one happy path: 调 refresh_token + apply_oauth_result
- refresh_one TokenExpiredError → 标 revoked
- refresh_one OAuthExchangeError → 保留 status, 失败计数
- refresh_one 密钥变化导致解密失败 → 标 revoked
- refresh_due_tokens 批量 + 统计
- 不刷 token_expires_at = NULL 的 connection
- 不刷 refresh_token_enc = NULL 的 connection
- 不刷 revoked / pending connection
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

from app.config import settings as settings_module
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im import token_refresher
from app.services.im.connector_base import (
    OAuthExchangeError,
    OAuthExchangeResult,
    TokenExpiredError,
)


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


def _seed_active_connection(
    expires_in_minutes: int = 2,
    with_refresh_token: bool = True,
):
    """种 active connection. expires_in_minutes 控制 expires_at."""
    conn = im_service.create_connection("p1", "feishu")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    im_service.apply_oauth_result(
        conn.id,
        OAuthExchangeResult(
            access_token="old-access",
            refresh_token="old-refresh" if with_refresh_token else None,
            expires_at=expires_at,
            tenant_name="t",
        ),
    )
    return im_service.get_connection(conn.id)


# ─── list_due_connections ───────────────────────────────────


def test_list_due_includes_expiring_soon() -> None:
    _seed_active_connection(expires_in_minutes=2)
    due = token_refresher.list_due_connections()
    assert len(due) == 1


def test_list_due_excludes_still_valid() -> None:
    _seed_active_connection(expires_in_minutes=60)  # 1 小时后 → 还远
    due = token_refresher.list_due_connections()
    assert due == []


def test_list_due_excludes_revoked() -> None:
    conn = _seed_active_connection(expires_in_minutes=2)
    im_service.update_status(conn.id, "revoked")
    due = token_refresher.list_due_connections()
    assert due == []


def test_list_due_excludes_no_refresh_token() -> None:
    _seed_active_connection(expires_in_minutes=2, with_refresh_token=False)
    due = token_refresher.list_due_connections()
    assert due == []


def test_list_due_excludes_pending() -> None:
    """status=pending → 还没真正 active,跳过."""
    conn = im_service.create_connection("p1", "feishu")
    # 不调 apply_oauth_result → 仍 pending
    due = token_refresher.list_due_connections()
    assert due == []


def test_list_due_excludes_no_expires_at() -> None:
    """expires_at=None (provider 没给) → 跳过."""
    conn = im_service.create_connection("p1", "feishu")
    im_service.apply_oauth_result(
        conn.id,
        OAuthExchangeResult(
            access_token="a", refresh_token="r", expires_at=None,
        ),
    )
    due = token_refresher.list_due_connections()
    assert due == []


# ─── refresh_one ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_one_happy_path() -> None:
    conn = _seed_active_connection(expires_in_minutes=2)
    new_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
    fake_result = OAuthExchangeResult(
        access_token="new-access",
        refresh_token="new-refresh",
        expires_at=new_expiry,
        tenant_name="t",
    )
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=AsyncMock(return_value=fake_result),
    ):
        ok, err = await token_refresher.refresh_one(conn)
    assert ok is True
    assert err is None
    # 复查: connection 已更新
    refreshed = im_service.get_connection(conn.id)
    assert im_crypto.decrypt_token(refreshed.auth_token_enc) == "new-access"
    assert im_crypto.decrypt_token(refreshed.refresh_token_enc) == "new-refresh"


@pytest.mark.asyncio
async def test_refresh_one_token_expired_marks_revoked() -> None:
    conn = _seed_active_connection(expires_in_minutes=2)
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=AsyncMock(side_effect=TokenExpiredError("refresh expired")),
    ):
        ok, err = await token_refresher.refresh_one(conn)
    assert ok is False
    assert "expired" in err
    refreshed = im_service.get_connection(conn.id)
    assert refreshed.status == "revoked"


@pytest.mark.asyncio
async def test_refresh_one_provider_error_keeps_status() -> None:
    """非 TokenExpired 的 provider 错 (e.g. 限流) → 保留 active."""
    conn = _seed_active_connection(expires_in_minutes=2)
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=AsyncMock(side_effect=OAuthExchangeError("rate limited")),
    ):
        ok, err = await token_refresher.refresh_one(conn)
    assert ok is False
    assert "rate limited" in err
    refreshed = im_service.get_connection(conn.id)
    assert refreshed.status == "active"


@pytest.mark.asyncio
async def test_refresh_one_decrypt_failure_marks_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主密钥变了 → 解密失败 → revoked."""
    conn = _seed_active_connection(expires_in_minutes=2)
    # 模拟密文损坏
    bad_conn = conn.model_copy(update={"refresh_token_enc": "garbled-not-hex"})
    im_service.get_registry().upsert(bad_conn)
    ok, err = await token_refresher.refresh_one(bad_conn)
    assert ok is False
    assert "decrypt" in err
    refreshed = im_service.get_connection(conn.id)
    assert refreshed.status == "revoked"


@pytest.mark.asyncio
async def test_refresh_one_unexpected_exception_logged() -> None:
    conn = _seed_active_connection(expires_in_minutes=2)
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        ok, err = await token_refresher.refresh_one(conn)
    assert ok is False
    assert "unexpected" in err


# ─── refresh_due_tokens ─────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_due_tokens_returns_stats() -> None:
    _seed_active_connection(expires_in_minutes=2)
    _seed_active_connection(expires_in_minutes=2)
    _seed_active_connection(expires_in_minutes=60)  # 不到期

    fake_result = OAuthExchangeResult(
        access_token="new", refresh_token="new",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=AsyncMock(return_value=fake_result),
    ):
        stats = await token_refresher.refresh_due_tokens()
    assert stats["checked"] == 2
    assert stats["ok"] == 2
    assert stats["failed"] == 0


@pytest.mark.asyncio
async def test_refresh_due_tokens_empty_returns_zero() -> None:
    stats = await token_refresher.refresh_due_tokens()
    assert stats == {"checked": 0, "ok": 0, "failed": 0}


@pytest.mark.asyncio
async def test_refresh_due_tokens_mixed_success_failure() -> None:
    _seed_active_connection(expires_in_minutes=2)
    _seed_active_connection(expires_in_minutes=2)

    call_count = {"i": 0}
    fake_result = OAuthExchangeResult(
        access_token="new", refresh_token="new",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )

    async def maybe_fail(self, rt):  # self 是 FeishuConnector 实例
        call_count["i"] += 1
        if call_count["i"] == 1:
            return fake_result
        raise OAuthExchangeError("simulated")

    with patch(
        "app.services.im.feishu_connector.FeishuConnector.refresh_token",
        new=maybe_fail,
    ):
        stats = await token_refresher.refresh_due_tokens()
    assert stats["checked"] == 2
    assert stats["ok"] == 1
    assert stats["failed"] == 1
