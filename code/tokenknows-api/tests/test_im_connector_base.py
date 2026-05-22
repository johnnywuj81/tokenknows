"""IMConnector ABC + Registry + IMNormalizedMessage (v0.3 T17).

覆盖:
- ABC 不可直接实例化
- 子类必须实现全部 abstract 方法
- IMNormalizedMessage 默认值 / dataclass 不可变 (frozen)
- Registry 注册 / 查询 / 多 platform 隔离
- ConnectorError 层级 isinstance 链
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest

from app.schemas.im import IMUser
from app.services.im.connector_base import (
    ConnectorError,
    ConnectorHealth,
    ConnectorRateLimitedError,
    IMConnector,
    IMNormalizedMessage,
    OAuthExchangeError,
    OAuthExchangeResult,
    TokenExpiredError,
    _ConnectorRegistry,
)


def test_im_normalized_message_minimal_construct() -> None:
    msg = IMNormalizedMessage(
        platform="feishu",
        platform_chat_id="chat-1",
        platform_msg_id="msg-1",
        sender=IMUser(user_id="u1", name="Alice"),
        content="hello",
    )
    assert msg.mentions == []
    assert msg.raw_event_type == "message"
    assert msg.platform == "feishu"


def test_im_normalized_message_is_frozen() -> None:
    msg = IMNormalizedMessage(
        platform="dingtalk", platform_chat_id="x", platform_msg_id="y",
        sender=None, content="hi",
    )
    with pytest.raises(FrozenInstanceError):
        msg.content = "changed"   # type: ignore[misc]


def test_connector_health_frozen() -> None:
    h = ConnectorHealth(ok=True, last_event_at=datetime.now(timezone.utc))
    assert h.ok is True
    assert h.error_count_1h == 0
    with pytest.raises(FrozenInstanceError):
        h.ok = False              # type: ignore[misc]


def test_oauth_exchange_result_required_access_token() -> None:
    """access_token 必填, refresh_token 可空 (飞书部分场景)."""
    r = OAuthExchangeResult(
        access_token="abc", refresh_token=None, expires_at=None,
    )
    assert r.access_token == "abc"
    assert r.refresh_token is None


def test_im_connector_is_abstract() -> None:
    """直接实例化 IMConnector 应失败."""
    with pytest.raises(TypeError, match="abstract"):
        IMConnector()   # type: ignore[abstract]


def test_im_connector_partial_subclass_still_abstract() -> None:
    """缺方法的子类不能实例化."""

    class HalfBaked(IMConnector):
        platform = "feishu"

        async def get_authorize_url(self, project_id, redirect_uri, state):
            return ""
        # 故意不实现剩下的

    with pytest.raises(TypeError, match="abstract"):
        HalfBaked()   # type: ignore[abstract]


def test_im_connector_full_subclass_instantiable() -> None:
    """实现所有 abstract 方法的子类可以实例化."""

    class FullConn(IMConnector):
        platform = "feishu"

        async def get_authorize_url(self, project_id, redirect_uri, state):
            return ""

        async def exchange_code(self, code):
            return OAuthExchangeResult(access_token="t", refresh_token=None, expires_at=None)

        async def refresh_token(self, refresh_token):
            return OAuthExchangeResult(access_token="t", refresh_token=None, expires_at=None)

        async def revoke(self):
            return None

        async def list_chats(self):
            return []

        async def add_bot_to_chat(self, chat_id):
            return None

        async def list_chat_members(self, chat_id):
            return []

        def fetch_history(self, chat_id, start_time, end_time) -> AsyncIterator[IMNormalizedMessage]:
            async def _it() -> AsyncIterator[IMNormalizedMessage]:
                if False:
                    yield IMNormalizedMessage(
                        platform="feishu", platform_chat_id="x",
                        platform_msg_id="y", sender=None, content="",
                    )
            return _it()

        def stream_messages(self, chat_id) -> AsyncIterator[IMNormalizedMessage]:
            async def _it() -> AsyncIterator[IMNormalizedMessage]:
                if False:
                    yield IMNormalizedMessage(
                        platform="feishu", platform_chat_id="x",
                        platform_msg_id="y", sender=None, content="",
                    )
            return _it()

        async def health(self):
            return ConnectorHealth(ok=True, last_event_at=None)

    inst = FullConn()
    assert inst.platform == "feishu"


# ─── ConnectorError 层级 ────────────────────────────────────


def test_oauth_error_isinstance_connector_error() -> None:
    e = OAuthExchangeError("code expired")
    assert isinstance(e, ConnectorError)


def test_token_expired_isinstance_connector_error() -> None:
    assert isinstance(TokenExpiredError("x"), ConnectorError)


def test_rate_limited_isinstance_connector_error() -> None:
    assert isinstance(ConnectorRateLimitedError("x"), ConnectorError)


# ─── Registry ───────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    reg = _ConnectorRegistry()

    class FakeFeishu(IMConnector):
        platform = "feishu"
        async def get_authorize_url(self, *a, **kw): return ""
        async def exchange_code(self, code): return OAuthExchangeResult("t", None, None)
        async def refresh_token(self, rt): return OAuthExchangeResult("t", None, None)
        async def revoke(self): pass
        async def list_chats(self): return []
        async def add_bot_to_chat(self, x): pass
        async def list_chat_members(self, x): return []
        def fetch_history(self, *a, **kw):
            async def _it(): yield  # type: ignore[misc]
            return _it()
        def stream_messages(self, *a, **kw):
            async def _it(): yield  # type: ignore[misc]
            return _it()
        async def health(self): return ConnectorHealth(ok=True, last_event_at=None)

    reg.register("feishu", FakeFeishu)
    assert reg.get("feishu") is FakeFeishu
    assert reg.get("dingtalk") is None


def test_registry_platforms_lists_all() -> None:
    reg = _ConnectorRegistry()

    class A(IMConnector):
        platform = "feishu"
        async def get_authorize_url(self, *a, **kw): return ""
        async def exchange_code(self, code): return OAuthExchangeResult("t", None, None)
        async def refresh_token(self, rt): return OAuthExchangeResult("t", None, None)
        async def revoke(self): pass
        async def list_chats(self): return []
        async def add_bot_to_chat(self, x): pass
        async def list_chat_members(self, x): return []
        def fetch_history(self, *a, **kw):
            async def _it(): yield  # type: ignore[misc]
            return _it()
        def stream_messages(self, *a, **kw):
            async def _it(): yield  # type: ignore[misc]
            return _it()
        async def health(self): return ConnectorHealth(ok=True, last_event_at=None)

    reg.register("feishu", A)
    reg.register("dingtalk", A)
    plats = set(reg.platforms())
    assert plats == {"feishu", "dingtalk"}


def test_registry_clear() -> None:
    reg = _ConnectorRegistry()
    reg._registry["feishu"] = type("X", (), {})  # type: ignore[assignment]
    reg.clear()
    assert reg.platforms() == []
