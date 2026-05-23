"""命令解析 + 限频 + TriggerSignal helper (v0.5.0 T45).

覆盖:
- parse_command: 5 windows × 3 subcommands happy 矩阵 + 6 类非法
- window_to_timedelta: 5 预设含 today/yesterday 跨日边界
- check_rate_limit: 单用户 5min / 同群 1h / 6 次 / 清理过期 / 跨群隔离
- build_signal_from_mention: TriggerSignal 字段完整 + Pydantic round-trip
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.auto_trigger import TriggerSignal
from app.services.auto_trigger.mention_dispatcher import (
    SUBCOMMAND_TO_ASSET_TYPE,
    VALID_SUBCOMMANDS,
    VALID_WINDOWS,
    ParseError,
    ParsedMention,
    build_signal_from_mention,
    check_rate_limit,
    parse_command,
    reset_rate_limit_state,
    window_to_timedelta,
)


# ─── parse_command happy ──────────────────────────────────


@pytest.mark.parametrize("subcommand", sorted(VALID_SUBCOMMANDS))
@pytest.mark.parametrize("window", sorted(VALID_WINDOWS))
def test_parse_command_happy_matrix(subcommand, window):
    """3 subcommand × 5 window = 15 个 happy case."""
    p = parse_command(f"/{subcommand} {window}")
    assert p.subcommand == subcommand
    assert p.window == window
    assert p.raw_text == f"/{subcommand} {window}"


def test_parse_command_multiple_spaces_ok():
    """split() 默认压缩多空格."""
    p = parse_command("/digest    2h")
    assert p.subcommand == "digest"
    assert p.window == "2h"


def test_parse_command_strip_ok():
    p = parse_command("   /distill today  ")
    assert p.subcommand == "distill"


# ─── parse_command 非法 (6 类) ────────────────────────────


def test_parse_empty_raises():
    with pytest.raises(ParseError, match="为空"):
        parse_command("")


def test_parse_blank_raises():
    with pytest.raises(ParseError, match="为空"):
        parse_command("   ")


def test_parse_missing_window_raises():
    with pytest.raises(ParseError, match="token"):
        parse_command("/digest")


def test_parse_no_slash_prefix_raises():
    with pytest.raises(ParseError, match="必须以 /"):
        parse_command("digest 2h")


def test_parse_unknown_subcommand_raises():
    with pytest.raises(ParseError, match="未知 subcommand"):
        parse_command("/dance 2h")


def test_parse_unknown_window_raises():
    with pytest.raises(ParseError, match="未知 window"):
        parse_command("/digest 3h")


def test_parse_extra_tokens_raises():
    with pytest.raises(ParseError, match="token"):
        parse_command("/digest 2h extra")


# ─── window_to_timedelta ─────────────────────────────────


def test_window_30m():
    assert window_to_timedelta("30m") == timedelta(minutes=30)


def test_window_2h():
    assert window_to_timedelta("2h") == timedelta(hours=2)


def test_window_7d():
    assert window_to_timedelta("7d") == timedelta(days=7)


def test_window_today_at_morning():
    """09:00 UTC 调 today → 9 小时."""
    now = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
    delta = window_to_timedelta("today", now=now)
    assert delta == timedelta(hours=9)


def test_window_today_at_midnight():
    """00:00:01 调 today → 1 秒."""
    now = datetime(2026, 5, 23, 0, 0, 1, tzinfo=timezone.utc)
    delta = window_to_timedelta("today", now=now)
    assert delta == timedelta(seconds=1)


def test_window_yesterday_morning():
    """周二 11:00 调 yesterday → 35 小时 (昨天 0 点至今)."""
    now = datetime(2026, 5, 23, 11, 0, tzinfo=timezone.utc)
    delta = window_to_timedelta("yesterday", now=now)
    assert delta == timedelta(days=1, hours=11)


# ─── build_signal_from_mention ───────────────────────────


def test_build_signal_complete_fields():
    p = ParsedMention(subcommand="digest", window="2h", raw_text="/digest 2h")
    sig = build_signal_from_mention(p, "oc_xxx", "ou_alice", "om_msg123")
    assert sig.type == "im_mention"
    assert sig.event_id == "msg-om_msg123"
    assert "alice" in sig.summary
    assert sig.payload["command"] == "digest"
    assert sig.payload["window"] == "2h"
    assert sig.payload["im_chat_id"] == "oc_xxx"
    assert sig.payload["triggered_by_user_id"] == "ou_alice"
    assert sig.payload["message_id"] == "om_msg123"


def test_build_signal_pydantic_roundtrip():
    """新 type='im_mention' 应能完整 Pydantic round-trip (兼容 v0.4 schema)."""
    p = ParsedMention(subcommand="skill", window="7d", raw_text="/skill 7d")
    sig = build_signal_from_mention(p, "oc_x", "ou_y", "om_z")
    raw = sig.model_dump_json()
    again = TriggerSignal.model_validate_json(raw)
    assert again.type == "im_mention"
    assert again.payload["window"] == "7d"


def test_subcommand_asset_type_mapping_complete():
    """3 个 subcommand 都有对应的 asset_type."""
    assert set(SUBCOMMAND_TO_ASSET_TYPE.keys()) == VALID_SUBCOMMANDS
    assert SUBCOMMAND_TO_ASSET_TYPE["digest"] == "weekly_report"
    assert SUBCOMMAND_TO_ASSET_TYPE["skill"] == "agent_skill"


# ─── check_rate_limit ────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_rl():
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


def test_rate_limit_first_call_allowed():
    r = check_rate_limit("chat1", "alice", now_ts=1000.0)
    assert r.allowed is True
    assert r.reason is None


def test_rate_limit_same_user_within_5min_denied():
    check_rate_limit("chat1", "alice", now_ts=1000.0)
    r2 = check_rate_limit("chat1", "alice", now_ts=1000.0 + 60)  # 1min 后
    assert r2.allowed is False
    assert "rate_limit_per_user_5min" in (r2.reason or "")


def test_rate_limit_same_user_after_5min_allowed():
    check_rate_limit("chat1", "alice", now_ts=1000.0)
    r2 = check_rate_limit("chat1", "alice", now_ts=1000.0 + 301)  # 5min+1s
    assert r2.allowed is True


def test_rate_limit_different_users_in_same_chat_independent():
    """同群不同用户的 5min 限频独立计数."""
    r1 = check_rate_limit("chat1", "alice", now_ts=1000.0)
    r2 = check_rate_limit("chat1", "bob", now_ts=1001.0)  # 同 chat, 不同 user
    assert r1.allowed is True
    assert r2.allowed is True


def test_rate_limit_same_user_different_chats_independent():
    """跨群同用户限频独立 (不同群独立计数)."""
    r1 = check_rate_limit("chat1", "alice", now_ts=1000.0)
    r2 = check_rate_limit("chat2", "alice", now_ts=1001.0)  # 同 user 不同 chat
    assert r1.allowed is True
    assert r2.allowed is True


def test_rate_limit_group_hour_cap():
    """同群 1h 6 次后第 7 次拒绝."""
    # 6 个不同 user 各发 1 次 (避免被单用户 5min 限制 dominated)
    for i in range(6):
        r = check_rate_limit("chat1", f"user{i}", now_ts=1000.0 + i * 10)
        assert r.allowed is True, f"第 {i+1} 次应允许, got {r.reason}"

    # 第 7 次
    r7 = check_rate_limit("chat1", "user6", now_ts=1000.0 + 60)
    assert r7.allowed is False
    assert "rate_limit_per_group_hour" in (r7.reason or "")


def test_rate_limit_group_hour_resets_after_3600s():
    """1h 后过期记录清理, 第 7 次允许."""
    for i in range(6):
        check_rate_limit("chat1", f"user{i}", now_ts=1000.0 + i)
    # 跳到 1h+1s 之后
    r = check_rate_limit("chat1", "user6", now_ts=1000.0 + 3601)
    assert r.allowed is True


def test_rate_limit_reset_state_clears_all():
    check_rate_limit("chat1", "alice", now_ts=1000.0)
    reset_rate_limit_state()
    r = check_rate_limit("chat1", "alice", now_ts=1001.0)
    assert r.allowed is True
