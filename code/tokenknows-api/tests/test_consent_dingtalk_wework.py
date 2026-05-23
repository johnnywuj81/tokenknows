"""T55 · 钉钉 ActionCard + 企微 textcard DM 实装.

覆盖:
- build_dingtalk_action_card payload 正确
- build_wework_textcard payload 正确
- _send_dm_dingtalk: degrade scenarios (no token / no agent_id / decrypt fail / 4xx / errcode≠0) + happy
- _send_dm_wework: 同上 + agentid
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.schemas.skill import Skill, SkillMetrics
from app.services.im.consent_notifier import (
    _send_dm_dingtalk_stub as _send_dm_dingtalk,
    _send_dm_wework_stub as _send_dm_wework,
    build_dingtalk_action_card,
    build_wework_textcard,
)


def _skill() -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id="skill-dt-1",
        project_id="proj-X",
        name="im-distilled-dt",
        version=1,
        skill_md="---\n---\n",
        embedding=None,
        metrics=SkillMetrics(),
        distilled_from=[],
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status="pending_contributor_consent",
        parent_skill_id=None,
        contributors=["uid-a", "uid-b"],
        consent_required_from=["uid-a", "uid-b"],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=now,
        created_at=now,
        updated_at=now,
    )


# ─── 模板 payload ─────────────────────────────────────────


def test_build_dingtalk_action_card_structure():
    card = build_dingtalk_action_card(_skill(), detail_url="https://x/skills/s1")
    assert "Skill 草稿等待你确认" in card["title"]
    assert card["btn_orientation"] == "1"
    assert len(card["btn_json_list"]) == 2
    assert card["btn_json_list"][0]["action_url"].endswith("?action=sign")
    assert card["btn_json_list"][1]["action_url"].endswith("?action=reject")
    assert "im-distilled-dt" in card["markdown"]
    assert "2 位贡献者" in card["markdown"]


def test_build_wework_textcard_structure():
    card = build_wework_textcard(_skill(), detail_url="https://x/skills/s1")
    assert "Skill 草稿等待确认" in card["title"]
    assert card["url"] == "https://x/skills/s1"
    assert card["btntxt"] == "查看详情"
    assert "<div class=\"highlight\">im-distilled-dt</div>" in card["description"]


# ─── 钉钉 _send_dm degrade ────────────────────────────────


def test_dingtalk_no_token_returns_false():
    out = _send_dm_dingtalk({"platform": "dingtalk"}, _skill(), "uid-a")
    assert out is False


def test_dingtalk_no_agent_id_returns_false():
    """有 token 无 agent_id → degrade web fallback."""
    out = _send_dm_dingtalk(
        {"platform": "dingtalk", "auth_token_enc": "x"},
        _skill(), "uid-a",
    )
    assert out is False


def test_dingtalk_decrypt_failure_returns_false(monkeypatch):
    from app.services import im_crypto

    def _raise(_):
        raise im_crypto.TokenCryptoError("bad")

    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token", _raise
    )
    out = _send_dm_dingtalk(
        {
            "platform": "dingtalk",
            "auth_token_enc": "x",
            "agent_id": 12345,
        },
        _skill(), "uid-a",
    )
    assert out is False


def test_dingtalk_http_4xx_returns_false(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-tok",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                502, content=b'{"errcode": 99}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_dingtalk(
        {
            "platform": "dingtalk",
            "auth_token_enc": "x",
            "agent_id": 12345,
        },
        _skill(), "uid-a",
    )
    assert out is False


def test_dingtalk_errcode_nonzero_returns_false(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-tok",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                200,
                content=json.dumps(
                    {"errcode": 60011, "errmsg": "no privilege"}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_dingtalk(
        {
            "platform": "dingtalk",
            "auth_token_enc": "x",
            "agent_id": 12345,
        },
        _skill(), "uid-a",
    )
    assert out is False


def test_dingtalk_happy_returns_true(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-tok",
    )
    sent = []

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            sent.append({
                "url": url, "params": k.get("params"), "json": k.get("json")
            })
            return httpx.Response(
                200,
                content=json.dumps(
                    {"errcode": 0, "errmsg": "ok", "task_id": 999}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_dingtalk(
        {
            "platform": "dingtalk",
            "auth_token_enc": "x",
            "agent_id": 12345,
        },
        _skill(), "uid-a",
    )
    assert out is True
    assert sent[0]["url"].endswith("/topapi/message/corpconversation/asyncsend_v2")
    assert sent[0]["params"]["access_token"] == "fake-tok"
    body = sent[0]["json"]
    assert body["agent_id"] == 12345
    assert body["userid_list"] == "uid-a"
    assert body["msg"]["msgtype"] == "action_card"
    assert len(body["msg"]["action_card"]["btn_json_list"]) == 2


def test_dingtalk_alt_field_name_dingtalk_agent_id(monkeypatch):
    """支持 connection_raw['dingtalk_agent_id'] 作为 agent_id 别名."""
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "tok",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                200, content=b'{"errcode":0}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_dingtalk(
        {
            "platform": "dingtalk",
            "auth_token_enc": "x",
            "dingtalk_agent_id": 6666,  # 用别名
        },
        _skill(), "uid-a",
    )
    assert out is True


# ─── 企微 _send_dm degrade ───────────────────────────────


def test_wework_no_token_returns_false():
    out = _send_dm_wework({"platform": "wework"}, _skill(), "uid-a")
    assert out is False


def test_wework_no_agentid_returns_false():
    out = _send_dm_wework(
        {"platform": "wework", "auth_token_enc": "x"},
        _skill(), "uid-a",
    )
    assert out is False


def test_wework_happy_returns_true(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-tok",
    )
    sent = []

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            sent.append({
                "url": url, "params": k.get("params"), "json": k.get("json")
            })
            return httpx.Response(
                200,
                content=json.dumps(
                    {"errcode": 0, "errmsg": "ok", "msgid": "MSG-1"}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_wework(
        {
            "platform": "wework",
            "auth_token_enc": "x",
            "agentid": 7777,
        },
        _skill(), "uid-a",
    )
    assert out is True
    assert sent[0]["url"].endswith("/cgi-bin/message/send")
    body = sent[0]["json"]
    assert body["touser"] == "uid-a"
    assert body["msgtype"] == "textcard"
    assert body["agentid"] == 7777
    assert "查看详情" in body["textcard"]["btntxt"]


def test_wework_errcode_nonzero_returns_false(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-tok",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                200,
                content=json.dumps(
                    {"errcode": 81013, "errmsg": "receiver not in agent"}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_wework(
        {
            "platform": "wework",
            "auth_token_enc": "x",
            "agentid": 7777,
        },
        _skill(), "uid-a",
    )
    assert out is False


def test_wework_alt_field_name_wework_agentid(monkeypatch):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "tok",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                200, content=b'{"errcode":0,"msgid":"M"}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )
    out = _send_dm_wework(
        {
            "platform": "wework",
            "auth_token_enc": "x",
            "wework_agentid": 8888,
        },
        _skill(), "uid-a",
    )
    assert out is True
