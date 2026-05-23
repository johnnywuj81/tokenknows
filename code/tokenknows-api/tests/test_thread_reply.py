"""IM 群内 Thread 回执 (v0.5.0 T47).

覆盖:
- build_reply_text: PUBLIC_BASE_URL 配 / 未配 / 含 user
- reply_in_thread 路由: feishu 完整 / dingtalk stub / wework stub / 未知 platform
- 飞书 _reply_feishu: token 缺失 / decrypt 失败 / HTTP 4xx / API code≠0 / happy
- dispatch_mention 接 thread_reply: 集成回归 (mock httpx)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services.im.thread_reply import (
    _reply_dingtalk_stub,
    _reply_feishu,
    _reply_wework_stub,
    build_reply_text,
    reply_in_thread,
)


# ─── build_reply_text ────────────────────────────────────


def test_reply_text_with_public_base_url(monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s.get_settings(), "public_base_url", "https://tokenknows.acme.com")
    text = build_reply_text(
        subcommand="digest", window="2h",
        execution_id="exec-1", project_id="proj-A", user_id="ou-alice",
    )
    assert "/digest 2h" in text
    assert "by ou-alice" in text
    assert "https://tokenknows.acme.com/projects/proj-A/auto-triggers/executions/exec-1" in text


def test_reply_text_without_public_base_url(monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s.get_settings(), "public_base_url", None)
    text = build_reply_text(
        subcommand="skill", window="7d",
        execution_id="exec-2", project_id="proj-B",
    )
    assert "execution=exec-2" in text
    assert "PUBLIC_BASE_URL 未配置" in text


def test_reply_text_without_user():
    text = build_reply_text(
        subcommand="distill", window="30m",
        execution_id="exec-3", project_id="proj-C",
    )
    assert "by" not in text  # 无 user 不含 "by xxx"


# ─── reply_in_thread 路由 ────────────────────────────────


def test_reply_route_unknown_platform_logs_and_returns_none():
    out = reply_in_thread(
        connection_raw={"platform": "weibo", "auth_token_enc": "x"},
        chat_id="c", parent_message_id="p", text="test",
    )
    assert out is None


def test_reply_route_dingtalk_stub():
    out = reply_in_thread(
        connection_raw={"platform": "dingtalk", "auth_token_enc": "x"},
        chat_id="c", parent_message_id="p", text="test",
    )
    assert out is None  # stub 返 None


def test_reply_route_wework_stub():
    out = reply_in_thread(
        connection_raw={"platform": "wework", "auth_token_enc": "x"},
        chat_id="c", parent_message_id="p", text="test",
    )
    assert out is None


def test_reply_route_exception_swallowed():
    """全局兜底: 任何异常都不抛."""
    # 制造异常: connection_raw 缺 platform 字段
    out = reply_in_thread(
        connection_raw={},  # 无 platform key
        chat_id="c", parent_message_id="p", text="test",
    )
    assert out is None  # platform="" 走 unknown 分支


# ─── 飞书 _reply_feishu ──────────────────────────────────


def test_feishu_no_token_returns_none():
    out = _reply_feishu(
        connection_raw={"platform": "feishu"},  # 无 auth_token_enc
        chat_id="oc-x", parent_message_id="om-y", text="hi",
    )
    assert out is None


def test_feishu_decrypt_failure_returns_none(monkeypatch):
    from app.services import im_crypto
    def _raise(_):
        raise im_crypto.TokenCryptoError("bad ciphertext")
    monkeypatch.setattr("app.services.im.thread_reply.decrypt_token", _raise)
    out = _reply_feishu(
        connection_raw={"platform": "feishu", "auth_token_enc": "deadbeef"},
        chat_id="oc-x", parent_message_id="om-y", text="hi",
    )
    assert out is None


def test_feishu_http_4xx_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.thread_reply.decrypt_token",
        lambda _: "fake-access-token",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            r = httpx.Response(403, content=b'{"code": 99, "msg": "forbidden"}')
            r._request = httpx.Request("POST", url)
            return r

    monkeypatch.setattr("app.services.im.thread_reply.httpx.Client", _MockClient)
    out = _reply_feishu(
        connection_raw={"platform": "feishu", "auth_token_enc": "x"},
        chat_id="oc-x", parent_message_id="om-y", text="hi",
    )
    assert out is None


def test_feishu_api_error_code_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.thread_reply.decrypt_token",
        lambda _: "fake-access-token",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                200,
                content=json.dumps(
                    {"code": 230002, "msg": "bot not in chat", "data": {}}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.services.im.thread_reply.httpx.Client", _MockClient)
    out = _reply_feishu(
        connection_raw={"platform": "feishu", "auth_token_enc": "x"},
        chat_id="oc-x", parent_message_id="om-y", text="hi",
    )
    assert out is None


def test_feishu_happy_returns_message_id(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.thread_reply.decrypt_token",
        lambda _: "fake-access-token",
    )

    sent_payloads: list[dict] = []

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            sent_payloads.append({"url": url, "json": k.get("json"), "headers": k.get("headers")})
            return httpx.Response(
                200,
                content=json.dumps(
                    {"code": 0, "msg": "", "data": {"message_id": "om-NEW-123"}}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.services.im.thread_reply.httpx.Client", _MockClient)
    out = _reply_feishu(
        connection_raw={"platform": "feishu", "auth_token_enc": "x"},
        chat_id="oc-x", parent_message_id="om-PARENT", text="hi 群里",
    )
    assert out == "om-NEW-123"
    # 验 POST URL 含 parent message_id
    assert "/messages/om-PARENT/reply" in sent_payloads[0]["url"]
    # body 含 msg_type / content / reply_in_thread
    body = sent_payloads[0]["json"]
    assert body["msg_type"] == "text"
    assert body["reply_in_thread"] is True
    # content 是 JSON-string of {text:...}
    content = json.loads(body["content"])
    assert content["text"] == "hi 群里"
    # headers 含 Bearer token
    assert sent_payloads[0]["headers"]["Authorization"] == "Bearer fake-access-token"


# ─── 集成: dispatch_mention 后调 thread_reply ────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


def _seed_feishu_connection(db, conn_id="conn-1", project_id="proj-X"):
    db.upsert_im_connection(
        connection_id=conn_id,
        project_id=project_id,
        platform="feishu",
        status="active",
        updated_at=datetime.now(timezone.utc).isoformat(),
        json_str=json.dumps({
            "id": conn_id, "project_id": project_id, "platform": "feishu",
            "status": "active",
            "auth_token_enc": "fake-encrypted-token",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }),
    )


def test_dispatch_mention_calls_thread_reply_on_success(fresh_db, monkeypatch):
    """dispatch_mention 成功 schedule 后, 应调 reply_in_thread (不阻塞主路径)."""
    from app.services.auto_trigger.mention_dispatcher import (
        GroupMentionEvent, dispatch_mention, reset_rate_limit_state,
    )
    reset_rate_limit_state()
    _seed_feishu_connection(fresh_db)

    called_with: list[dict] = []
    def _fake_reply(*, connection_raw, chat_id, parent_message_id, text):
        called_with.append({
            "chat_id": chat_id, "parent": parent_message_id, "text": text,
        })
        return "om-NEW-1"

    monkeypatch.setattr(
        "app.services.im.thread_reply.reply_in_thread", _fake_reply,
    )

    ev = GroupMentionEvent(
        platform="feishu", chat_id="oc-x", user_id="ou-alice",
        message_id="om-PARENT", command_text="/digest 2h",
    )
    result = dispatch_mention(ev, "conn-1")
    assert result.ok is True
    assert result.execution_id is not None

    # thread_reply 被调用 1 次, parent 正确
    assert len(called_with) == 1
    assert called_with[0]["parent"] == "om-PARENT"
    assert "/digest 2h" in called_with[0]["text"]
    assert result.execution_id in called_with[0]["text"]  # link 含 execution_id


def test_dispatch_mention_thread_reply_failure_does_not_break(fresh_db, monkeypatch):
    """reply_in_thread 抛异常时, dispatch_mention 仍返回 ok=True (asset 已 schedule)."""
    from app.services.auto_trigger.mention_dispatcher import (
        GroupMentionEvent, dispatch_mention, reset_rate_limit_state,
    )
    reset_rate_limit_state()
    _seed_feishu_connection(fresh_db)

    def _raise(**k):
        raise RuntimeError("network down")
    monkeypatch.setattr(
        "app.services.im.thread_reply.reply_in_thread", _raise,
    )

    ev = GroupMentionEvent(
        platform="feishu", chat_id="oc-x", user_id="ou-alice",
        message_id="om-P", command_text="/skill today",
    )
    result = dispatch_mention(ev, "conn-1")
    assert result.ok is True  # 主路径仍成功
    assert result.execution_id is not None


def test_dispatch_mention_no_connection_skips_thread_reply(fresh_db, monkeypatch):
    """connection 查不到时, 不调 reply_in_thread."""
    # 不 seed connection
    from app.services.auto_trigger.mention_dispatcher import (
        GroupMentionEvent, dispatch_mention, reset_rate_limit_state,
    )
    reset_rate_limit_state()

    called = [False]
    def _track(**k):
        called[0] = True
        return "om-x"
    monkeypatch.setattr(
        "app.services.im.thread_reply.reply_in_thread", _track,
    )

    ev = GroupMentionEvent(
        platform="feishu", chat_id="oc-x", user_id="ou-alice",
        message_id="om-P", command_text="/digest 2h",
    )
    result = dispatch_mention(ev, "conn-NOT-EXIST")
    # 主流程是 no_project (因为 resolve_project_for_chat 返 None)
    assert result.ok is False
    assert result.error == "no_project"
    # thread_reply 不应被调用 (因为主流程已经在 schedule 之前失败)
    assert called[0] is False
