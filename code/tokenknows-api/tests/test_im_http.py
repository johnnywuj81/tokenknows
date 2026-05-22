"""IM REST API HTTP integration (v0.3 T23).

覆盖 11 端点 happy + 错误路径:
- POST /projects/:id/im/connections (201 + authorize_url)
- GET /projects/:id/im/connections (list + status filter)
- GET /im/connections/:id (404 ghost)
- PATCH /im/connections/:id (400 if status missing)
- DELETE /im/connections/:id (revoke)
- GET /im/connections/:id/chats (401 if no token, 404 ghost)
- POST .../chats/:cid/join (mock add_bot)
- POST .../chats/:cid/leave
- GET .../chats/:cid/stats
- GET .../messages (include_content=False 默认隐藏)
- POST .../distill (按需触发)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    s = settings_module.get_settings()
    s.im_encryption_key = Fernet.generate_key().decode()
    s.feishu_app_id = "cli_test"
    s.feishu_app_secret = "secret-y"
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ─── 创建 + 列表 + 详情 + 更新 + 撤回 ─────────────────────


def test_create_connection_returns_authorize_url(client: TestClient) -> None:
    r = client.post(
        "/api/v1/projects/p1/im/connections",
        json={"platform": "feishu"},
    )
    assert r.status_code == 201
    data = r.json()
    assert "authorize_url" in data
    assert "authen/v1/authorize" in data["authorize_url"]
    assert data["connection"]["status"] == "pending"
    assert data["connection"]["platform"] == "feishu"


def test_create_connection_no_app_creds_returns_warning_url(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings_module.get_settings(), "feishu_app_id", None)
    r = client.post(
        "/api/v1/projects/p1/im/connections",
        json={"platform": "feishu"},
    )
    assert r.status_code == 201
    assert r.json()["authorize_url"].startswith("#im-not-configured")


def test_list_connections_filters_by_status(client: TestClient) -> None:
    c1 = im_service.create_connection("p1", "feishu")
    c2 = im_service.create_connection("p1", "feishu")
    im_service.update_status(c2.id, "active")
    r = client.get("/api/v1/projects/p1/im/connections?status=active")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert ids == [c2.id]


def test_get_connection_404_when_missing(client: TestClient) -> None:
    r = client.get("/api/v1/im/connections/ghost")
    assert r.status_code == 404


def test_get_connection_returns_full_dump(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.get(f"/api/v1/im/connections/{c.id}")
    assert r.status_code == 200
    assert r.json()["id"] == c.id


def test_patch_connection_400_when_status_missing(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.patch(f"/api/v1/im/connections/{c.id}", json={})
    assert r.status_code == 400


def test_patch_connection_updates_status(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.patch(
        f"/api/v1/im/connections/{c.id}", json={"status": "active"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_delete_connection_revokes_not_deletes(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.delete(f"/api/v1/im/connections/{c.id}")
    assert r.status_code == 204
    refreshed = im_service.get_connection(c.id)
    assert refreshed is not None
    assert refreshed.status == "revoked"
    assert refreshed.revoked_at is not None


def test_delete_connection_404_when_missing(client: TestClient) -> None:
    r = client.delete("/api/v1/im/connections/ghost")
    assert r.status_code == 404


# ─── 群 ──────────────────────────────────────────────────────


def test_list_chats_404_when_connection_missing(client: TestClient) -> None:
    r = client.get("/api/v1/im/connections/ghost/chats")
    assert r.status_code == 404


def test_list_chats_401_when_no_token(client: TestClient) -> None:
    """connection 没 OAuth → token 缺 → 401."""
    c = im_service.create_connection("p1", "feishu")
    r = client.get(f"/api/v1/im/connections/{c.id}/chats")
    assert r.status_code == 401


def test_list_chats_happy_path(client: TestClient) -> None:
    from app.services.im.connector_base import OAuthExchangeResult
    c = im_service.create_connection("p1", "feishu")
    im_service.apply_oauth_result(c.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
    ))
    fake_chats = [{"chat_id": "oc_a", "name": "群一"}]
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.list_chats",
        new=AsyncMock(return_value=fake_chats),
    ):
        r = client.get(f"/api/v1/im/connections/{c.id}/chats")
    assert r.status_code == 200
    assert r.json() == fake_chats


def test_join_chat_calls_add_bot(client: TestClient) -> None:
    from app.services.im.connector_base import OAuthExchangeResult
    c = im_service.create_connection("p1", "feishu")
    im_service.apply_oauth_result(c.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
    ))
    with patch(
        "app.services.im.feishu_connector.FeishuConnector.add_bot_to_chat",
        new=AsyncMock(return_value=None),
    ) as m:
        r = client.post(f"/api/v1/im/connections/{c.id}/chats/oc_a/join")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    m.assert_awaited_once_with("oc_a")


def test_leave_chat_is_local_marker(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.post(f"/api/v1/im/connections/{c.id}/chats/oc_a/leave")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat_stats_counts_and_contributors(
    client: TestClient, fresh_state: SqliteStore
) -> None:
    c = im_service.create_connection("p1", "feishu")
    # seed 3 messages: 2 from Alice (1 signal), 1 from Bob
    base_msg = {
        "platform_chat_id": "oc_a",
        "mentions": [], "received_at": "2026-05-22T10:00:00+00:00",
    }
    fresh_state.insert_im_message(
        message_id="m1", connection_id=c.id, platform_chat_id="oc_a",
        platform_msg_id="r1", received_at="2026-05-22T10:00:00+00:00",
        retention_until=None, is_signal=True, redacted=False,
        json_str=json.dumps({
            **base_msg, "id": "m1", "platform_msg_id": "r1",
            "sender": {"user_id": "u-alice", "name": "Alice"},
            "content": "决定" * 30, "is_signal": True,
        }),
    )
    fresh_state.insert_im_message(
        message_id="m2", connection_id=c.id, platform_chat_id="oc_a",
        platform_msg_id="r2", received_at="2026-05-22T10:01:00+00:00",
        retention_until=None, is_signal=False, redacted=False,
        json_str=json.dumps({
            **base_msg, "id": "m2", "platform_msg_id": "r2",
            "sender": {"user_id": "u-alice", "name": "Alice"},
            "content": "ok", "is_signal": False,
        }),
    )
    fresh_state.insert_im_message(
        message_id="m3", connection_id=c.id, platform_chat_id="oc_a",
        platform_msg_id="r3", received_at="2026-05-22T10:02:00+00:00",
        retention_until=None, is_signal=False, redacted=False,
        json_str=json.dumps({
            **base_msg, "id": "m3", "platform_msg_id": "r3",
            "sender": {"user_id": "u-bob", "name": "Bob"},
            "content": "我看也是", "is_signal": False,
        }),
    )

    r = client.get(f"/api/v1/im/connections/{c.id}/chats/oc_a/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["message_count"] == 3
    assert data["signal_count"] == 1
    assert abs(data["signal_rate"] - 0.333) < 0.01
    top = {t["user_id"]: t["messages"] for t in data["top_contributors"]}
    assert top["u-alice"] == 2
    assert top["u-bob"] == 1


# ─── 消息列表 ────────────────────────────────────────────────


def test_list_messages_hides_content_by_default(
    client: TestClient, fresh_state: SqliteStore
) -> None:
    c = im_service.create_connection("p1", "feishu")
    fresh_state.insert_im_message(
        message_id="m1", connection_id=c.id, platform_chat_id="oc_a",
        platform_msg_id="r1", received_at="2026-05-22T10:00:00+00:00",
        retention_until=None, is_signal=False, redacted=False,
        json_str=json.dumps({
            "id": "m1", "platform_chat_id": "oc_a", "platform_msg_id": "r1",
            "sender": {"user_id": "u1"}, "content": "敏感原文",
            "mentions": [], "received_at": "2026-05-22T10:00:00+00:00",
        }),
    )
    r = client.get(f"/api/v1/im/connections/{c.id}/messages")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["content"] is None


def test_list_messages_with_content_flag(
    client: TestClient, fresh_state: SqliteStore
) -> None:
    c = im_service.create_connection("p1", "feishu")
    fresh_state.insert_im_message(
        message_id="m1", connection_id=c.id, platform_chat_id="oc_a",
        platform_msg_id="r1", received_at="2026-05-22T10:00:00+00:00",
        retention_until=None, is_signal=False, redacted=False,
        json_str=json.dumps({
            "id": "m1", "platform_chat_id": "oc_a", "platform_msg_id": "r1",
            "sender": {"user_id": "u1"}, "content": "真实内容",
            "mentions": [], "received_at": "2026-05-22T10:00:00+00:00",
        }),
    )
    r = client.get(
        f"/api/v1/im/connections/{c.id}/messages?include_content=true"
    )
    assert r.status_code == 200
    assert r.json()[0]["content"] == "真实内容"


# ─── distill ────────────────────────────────────────────────


def test_distill_no_messages_returns_zero(client: TestClient) -> None:
    c = im_service.create_connection("p1", "feishu")
    r = client.post(
        f"/api/v1/im/connections/{c.id}/distill",
        json={"chat_id": "ghost"},
    )
    assert r.status_code == 200
    assert r.json() == {"segments_persisted": 0, "segment_ids": []}


def test_distill_creates_value_segments(
    client: TestClient, fresh_state: SqliteStore
) -> None:
    c = im_service.create_connection("p1", "feishu")
    # seed 3 long signal-eligible messages
    contents = [
        "决定使用 pgvector 作为向量存储引擎,因为已经在 PG 里有完整 schema, 详细见 ADR",
        "同意,而且 pgvector 也支持 HNSW 索引,生产性能完全够用,推荐方案",
        "已落实到 ADR-005 文档,下周开始集成,worker pool 配置同步调整",
    ]
    for i, content in enumerate(contents):
        fresh_state.insert_im_message(
            message_id=f"m{i}", connection_id=c.id, platform_chat_id="oc_a",
            platform_msg_id=f"r{i}",
            received_at=f"2026-05-22T10:0{i}:00+00:00",
            retention_until=None, is_signal=False, redacted=False,
            json_str=json.dumps({
                "id": f"m{i}", "platform_chat_id": "oc_a",
                "platform_msg_id": f"r{i}",
                "sender": {"user_id": f"u{i}", "name": f"User{i}"},
                "content": content,
                "mentions": [],
                "received_at": f"2026-05-22T10:0{i}:00+00:00",
            }),
        )
    r = client.post(
        f"/api/v1/im/connections/{c.id}/distill",
        json={"chat_id": "oc_a", "source_mode": "assistant"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["segments_persisted"] >= 1
    # value_segments 表里应有相应记录
    rows = fresh_state.list_value_segments("p1")
    assert len(rows) == data["segments_persisted"]


def test_distill_404_when_connection_missing(client: TestClient) -> None:
    r = client.post(
        "/api/v1/im/connections/ghost/distill",
        json={"chat_id": "oc_a"},
    )
    assert r.status_code == 404
