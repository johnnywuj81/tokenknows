"""T46 · MentionDispatcher + IM Webhook 集成.

覆盖:
- _strip_at_prefix: 飞书 @_user_1 占位 / 钉钉 @TokenKnows 文本 / 缺 / 兜底
- normalize_im_mention:
  * bot 未配置 → None
  * 无 mentions → None
  * mentions 不含 bot → None
  * 含 bot + 无 sender → None
  * happy path
- resolve_project_for_chat: 命中 / 未绑定 / 不存在 connection
- dispatch_mention 主流程:
  * parse_error → DispatchResult(ok=False, hint=...)
  * rate_limit → ok=False
  * no_project → ok=False
  * happy → schedule_execution 真入库 + ok=True + execution_id
- 集成: 同一 webhook 调用 normalize + dispatch 全链路 (mock IMNormalizedMessage)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.mention_dispatcher import (
    DispatchResult,
    GroupMentionEvent,
    _strip_at_prefix,
    dispatch_mention,
    normalize_im_mention,
    reset_rate_limit_state,
    resolve_project_for_chat,
)


# ─── Mock IMNormalizedMessage (避免依赖完整 v0.3 connector_base) ──


@dataclass
class _FakeSender:
    user_id: str
    name: str | None = None


@dataclass
class _FakeIMMsg:
    """足够 normalize_im_mention 用的最小化对象."""
    platform: str
    platform_chat_id: str
    platform_msg_id: str
    sender: _FakeSender | None
    content: str
    mentions: list[str]


def _make_msg(
    *,
    chat="oc-chat-1",
    msg_id="om-msg-1",
    sender_id="ou-alice",
    content="@_user_1 /digest 2h",
    mentions=("ou-bot",),
    platform="feishu",
) -> _FakeIMMsg:
    return _FakeIMMsg(
        platform=platform,
        platform_chat_id=chat,
        platform_msg_id=msg_id,
        sender=_FakeSender(user_id=sender_id) if sender_id else None,
        content=content,
        mentions=list(mentions),
    )


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


@pytest.fixture(autouse=True)
def reset_rl():
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


def _seed_connection(db, conn_id="conn-1", project_id="proj-mentions"):
    """直接 SQL upsert im_connection (跳过完整 OAuth)."""
    import json
    db.upsert_im_connection(
        connection_id=conn_id,
        project_id=project_id,
        platform="feishu",
        status="active",
        updated_at=datetime.now(timezone.utc).isoformat(),
        json_str=json.dumps({
            "id": conn_id, "project_id": project_id, "platform": "feishu",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }),
    )


# ─── _strip_at_prefix ────────────────────────────────────


def test_strip_at_prefix_feishu_placeholder():
    """飞书 content 里可能含 @_user_1 占位符 + 命令."""
    assert _strip_at_prefix("@_user_1 /digest 2h") == "/digest 2h"


def test_strip_at_prefix_dingtalk_bot_name():
    assert _strip_at_prefix("@TokenKnows /skill today") == "/skill today"


def test_strip_at_prefix_already_clean():
    assert _strip_at_prefix("/distill 7d") == "/distill 7d"


def test_strip_at_prefix_empty():
    assert _strip_at_prefix("") == ""
    assert _strip_at_prefix(None) == ""  # type: ignore[arg-type]


def test_strip_at_prefix_no_slash():
    """无 / 的文本: 整体 strip 返回 (后续 parse_command 会拒)."""
    assert _strip_at_prefix("just text") == "just text"


# ─── normalize_im_mention ────────────────────────────────


def test_normalize_no_bot_user_id_returns_none():
    msg = _make_msg()
    assert normalize_im_mention(msg, None) is None
    assert normalize_im_mention(msg, "") is None


def test_normalize_no_mentions_returns_none():
    msg = _make_msg(mentions=())
    assert normalize_im_mention(msg, "ou-bot") is None


def test_normalize_mentions_no_bot_returns_none():
    """有 @ 但没 @ bot."""
    msg = _make_msg(mentions=("ou-other",))
    assert normalize_im_mention(msg, "ou-bot") is None


def test_normalize_no_sender_returns_none():
    """sender 缺失 → 不能审计 + 限频, 返 None."""
    msg = _make_msg(sender_id="")  # 显式 empty
    # 上面 _make_msg 把 empty 当 None 处理
    msg.sender = None
    assert normalize_im_mention(msg, "ou-bot") is None


def test_normalize_happy_returns_event():
    msg = _make_msg(content="@_user_1 /digest 2h")
    ev = normalize_im_mention(msg, "ou-bot")
    assert ev is not None
    assert ev.platform == "feishu"
    assert ev.chat_id == "oc-chat-1"
    assert ev.user_id == "ou-alice"
    assert ev.command_text == "/digest 2h"
    assert "ou-bot" in ev.raw_mentions


def test_normalize_truncates_oversize_command():
    huge_content = "/digest 2h" + (" extra" * 100)  # ~ 700 chars
    msg = _make_msg(content=huge_content)
    ev = normalize_im_mention(msg, "ou-bot")
    assert ev is not None
    assert len(ev.command_text) <= 200  # _MAX_COMMAND_LEN


# ─── resolve_project_for_chat ────────────────────────────


def test_resolve_project_found(fresh_db):
    _seed_connection(fresh_db, conn_id="conn-A", project_id="proj-X")
    assert resolve_project_for_chat("conn-A") == "proj-X"


def test_resolve_project_unknown_connection(fresh_db):
    assert resolve_project_for_chat("conn-nope") is None


# ─── dispatch_mention 主流程 ─────────────────────────────


def _event(**overrides) -> GroupMentionEvent:
    defaults = dict(
        platform="feishu",
        chat_id="oc-x",
        user_id="ou-alice",
        message_id="om-1",
        command_text="/digest 2h",
        raw_mentions=("ou-bot",),
    )
    defaults.update(overrides)
    return GroupMentionEvent(**defaults)


def test_dispatch_parse_error_returns_hint(fresh_db):
    _seed_connection(fresh_db)
    r = dispatch_mention(_event(command_text="bogus"), "conn-1")
    assert r.ok is False
    assert r.error == "parse_error"
    assert r.hint and "TokenKnows" in r.hint


def test_dispatch_rate_limited(fresh_db):
    _seed_connection(fresh_db)
    # 第一次: ok
    r1 = dispatch_mention(_event(), "conn-1")
    assert r1.ok is True

    # 第二次同用户: 5min 内拒
    r2 = dispatch_mention(_event(message_id="om-2"), "conn-1")
    assert r2.ok is False
    assert r2.error == "rate_limited"


def test_dispatch_no_project_binding(fresh_db):
    # 不 seed connection → resolve_project_for_chat 返 None
    r = dispatch_mention(_event(), "conn-not-bound")
    assert r.ok is False
    assert r.error == "no_project"
    assert "项目" in (r.hint or "")


def test_dispatch_happy_creates_execution(fresh_db):
    _seed_connection(fresh_db, conn_id="conn-1", project_id="proj-mentions")
    r = dispatch_mention(_event(), "conn-1")
    assert r.ok is True
    assert r.execution_id is not None
    # execution 真入库
    exe = svc.get_execution(r.execution_id)
    assert exe is not None
    assert exe.project_id == "proj-mentions"
    assert exe.status == "scheduled"
    assert exe.signal.type == "im_mention"
    # withdraw_window_min=0 → fire_at ≈ now (不是 5min 后)
    delta = (exe.fire_at - datetime.now(timezone.utc)).total_seconds()
    assert -1 <= delta <= 5  # 立即可 fire


def test_dispatch_all_subcommands_route_to_correct_asset_type(fresh_db):
    _seed_connection(fresh_db, conn_id="conn-1", project_id="proj-X")

    cases = [
        ("/distill 30m", "value_segments_only"),
        ("/digest 2h", "weekly_report"),
        ("/skill 7d", "agent_skill"),
    ]
    for cmd, expected_asset_type in cases:
        reset_rate_limit_state()
        r = dispatch_mention(
            _event(
                command_text=cmd,
                user_id=f"u-{cmd}",     # 不同 user 避免限频
                message_id=f"m-{cmd}",
            ),
            "conn-1",
        )
        assert r.ok is True, f"{cmd} 失败: {r.reason}"
        exe = svc.get_execution(r.execution_id)
        # virtual rule id 含 subcommand 名
        subcommand = cmd.split()[0].lstrip("/")
        assert subcommand in exe.rule_id, f"{cmd}: rule_id={exe.rule_id}"


# ─── 端到端集成 ──────────────────────────────────────────


def test_e2e_normalize_then_dispatch(fresh_db):
    """webhook 的完整链路: IMNormalizedMessage → normalize → dispatch → execution 入库."""
    _seed_connection(fresh_db, conn_id="conn-e2e", project_id="proj-e2e")

    msg = _make_msg(content="@_user_1 /skill today")
    ev = normalize_im_mention(msg, "ou-bot")
    assert ev is not None

    r = dispatch_mention(ev, "conn-e2e")
    assert r.ok is True
    exe = svc.get_execution(r.execution_id)
    assert exe.signal.payload["command"] == "skill"
    assert exe.signal.payload["window"] == "today"
    assert exe.signal.payload["im_chat_id"] == "oc-chat-1"
