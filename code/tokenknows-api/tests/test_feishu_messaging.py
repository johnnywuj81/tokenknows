"""FeishuConnector 消息能力 (v0.3 T19).

覆盖:
- list_chats 解析 data.items
- list_chats 401 → TokenExpiredError
- add_bot_to_chat POST 体含 app_id
- list_chat_members 归一化
- fetch_history 翻页 (page_token 链)
- fetch_history 空 chat
- _normalize_message text/post/system/mentions/timestamp
- _get_with_token / _post_with_token 缺 token → TokenExpiredError
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings as settings_module
from app.services.im.connector_base import (
    ConnectorError,
    TokenExpiredError,
)
from app.services.im.feishu_connector import FeishuConnector


@pytest.fixture
def with_creds(monkeypatch: pytest.MonkeyPatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "feishu_app_id", "cli_x")
    monkeypatch.setattr(s, "feishu_app_secret", "secret-y")
    yield


# ─── 鉴权前置 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_without_token_raises_token_expired(with_creds) -> None:
    conn = FeishuConnector(access_token=None)
    with pytest.raises(TokenExpiredError):
        await conn.list_chats()


@pytest.mark.asyncio
async def test_post_without_token_raises_token_expired(with_creds) -> None:
    conn = FeishuConnector(access_token=None)
    with pytest.raises(TokenExpiredError):
        await conn.add_bot_to_chat("chat-1")


# ─── list_chats ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_chats_parses_items(with_creds) -> None:
    fake_payload = {
        "code": 0,
        "data": {
            "items": [
                {"chat_id": "oc_abc", "name": "技术群", "chat_type": "group"},
                {"chat_id": "oc_def", "name": "私聊", "chat_type": "p2p"},
            ]
        },
    }
    fake_resp = httpx.Response(200, json=fake_payload, request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        chats = await conn.list_chats()
    assert [c["chat_id"] for c in chats] == ["oc_abc", "oc_def"]


@pytest.mark.asyncio
async def test_list_chats_401_raises_token_expired(with_creds) -> None:
    fake_resp = httpx.Response(401, text="unauthorized",
                                request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(TokenExpiredError):
            await conn.list_chats()


@pytest.mark.asyncio
async def test_list_chats_5xx_raises_connector_error(with_creds) -> None:
    fake_resp = httpx.Response(500, text="srv error",
                                request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(ConnectorError, match="HTTP 500"):
            await conn.list_chats()


@pytest.mark.asyncio
async def test_list_chats_non_zero_code_raises(with_creds) -> None:
    fake_payload = {"code": 1234, "msg": "rate limited"}
    fake_resp = httpx.Response(200, json=fake_payload,
                                request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(ConnectorError, match="code=1234"):
            await conn.list_chats()


# ─── add_bot_to_chat ────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_bot_to_chat_sends_app_id(with_creds) -> None:
    captured: dict = {}

    async def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["body"] = json
        return httpx.Response(200, json={"code": 0, "data": {}},
                              request=httpx.Request("POST", url))

    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(side_effect=fake_post)):
        await conn.add_bot_to_chat("chat-x")
    assert "chat-x" in captured["url"]
    assert captured["body"]["id_list"] == ["cli_x"]
    assert captured["body"]["member_id_type"] == "app_id"


# ─── list_chat_members ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_chat_members_normalizes_to_imuser(with_creds) -> None:
    fake_payload = {
        "code": 0,
        "data": {
            "items": [
                {"member_id": "u1", "name": "Alice"},
                {"open_id": "u2", "name": "Bob"},
            ]
        },
    }
    fake_resp = httpx.Response(200, json=fake_payload,
                                request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        members = await conn.list_chat_members("chat-x")
    assert len(members) == 2
    assert members[0].user_id == "u1"
    assert members[1].user_id == "u2"
    assert members[0].name == "Alice"


# ─── fetch_history ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_history_traverses_pages(with_creds) -> None:
    """模拟 2 页 → 第二页无 page_token 终止."""
    responses = [
        httpx.Response(200, json={
            "code": 0,
            "data": {
                "items": [
                    _raw_text_message("m1", "text content one"),
                    _raw_text_message("m2", "text content two"),
                ],
                "page_token": "next-token-1",
            },
        }, request=httpx.Request("GET", "http://x")),
        httpx.Response(200, json={
            "code": 0,
            "data": {
                "items": [_raw_text_message("m3", "text content three")],
                "page_token": None,
            },
        }, request=httpx.Request("GET", "http://x")),
    ]
    call_count = {"i": 0}

    async def fake_get(url, params=None, headers=None):
        idx = call_count["i"]
        call_count["i"] += 1
        return responses[idx]

    conn = FeishuConnector(access_token="ut")
    now = datetime.now(timezone.utc)
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)):
        msgs = [
            m async for m in conn.fetch_history(
                "chat-x", now - timedelta(days=1), now,
            )
        ]
    assert len(msgs) == 3
    assert [m.platform_msg_id for m in msgs] == ["m1", "m2", "m3"]
    assert all(m.platform == "feishu" for m in msgs)
    # 翻页发生了
    assert call_count["i"] == 2


@pytest.mark.asyncio
async def test_fetch_history_empty_chat_returns_zero(with_creds) -> None:
    fake_resp = httpx.Response(200, json={
        "code": 0, "data": {"items": [], "page_token": None}
    }, request=httpx.Request("GET", "http://x"))
    conn = FeishuConnector(access_token="ut")
    now = datetime.now(timezone.utc)
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=fake_resp)):
        msgs = [
            m async for m in conn.fetch_history(
                "chat-x", now - timedelta(days=1), now,
            )
        ]
    assert msgs == []


# ─── _normalize_message ────────────────────────────────────


def test_normalize_text_message() -> None:
    raw = _raw_text_message("m1", "hello world")
    conn = FeishuConnector()
    msg = conn._normalize_message(raw, "chat-x")
    assert msg is not None
    assert msg.platform == "feishu"
    assert msg.content == "hello world"
    assert msg.sender.user_id == "u-alice"


def test_normalize_skips_non_text_types() -> None:
    raw = {"msg_type": "image", "message_id": "m1"}
    conn = FeishuConnector()
    assert conn._normalize_message(raw, "chat-x") is None


def test_normalize_skips_empty_content() -> None:
    raw = {
        "msg_type": "text",
        "message_id": "m1",
        "body": {"content": ""},
        "sender": {"id": "u"},
    }
    conn = FeishuConnector()
    assert conn._normalize_message(raw, "chat-x") is None


def test_normalize_captures_mentions() -> None:
    raw = _raw_text_message("m1", "@bob 看看")
    raw["mentions"] = [{"id": "u-bob"}]
    conn = FeishuConnector()
    msg = conn._normalize_message(raw, "chat-x")
    assert msg.mentions == ["u-bob"]


def test_normalize_parses_create_time_ms() -> None:
    raw = _raw_text_message("m1", "hi")
    raw["create_time"] = "1716370800000"  # 2024-05-22T...
    conn = FeishuConnector()
    msg = conn._normalize_message(raw, "chat-x")
    assert msg is not None
    assert msg.received_at.year >= 2024


def _raw_text_message(msg_id: str, text: str) -> dict:
    return {
        "msg_type": "text",
        "message_id": msg_id,
        "body": {"content": {"text": text}},
        "sender": {"id": "u-alice", "name": "Alice"},
        "create_time": "1716370800000",
    }
