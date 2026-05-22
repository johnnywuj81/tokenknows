"""IM schema (Pydantic) + persistence CRUD (v0.3 T16).

覆盖:
- IMConnection / IMMessage / ValueSegment round-trip
- IMPlatform / IMConnectionStatus / IMSourceMode Literal 边界
- ValueSegmentSource 嵌套 source.mode / im_message_ids
- SqliteStore.upsert_im_connection / list / get / delete (带 cascade)
- insert_im_message INSERT OR IGNORE 幂等
- list_im_messages 过滤 (chat / since/until / signal_only)
- expire_im_messages retention 扫描
- mark_im_message_redacted
- upsert_value_segment + list_value_segments (按 trust DESC)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.persistence.store import SqliteStore
from app.schemas.im import (
    IMConnection,
    IMMessage,
    IMUser,
    ValueSegment,
    ValueSegmentSource,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Schema ─────────────────────────────────────────────────


def test_im_connection_construct_defaults() -> None:
    c = IMConnection(
        id="conn-1",
        project_id="proj-1",
        platform="feishu",
        created_at=_now(),
        updated_at=_now(),
    )
    assert c.status == "pending"
    assert c.auth_token_enc is None
    assert c.consent_signed_at is None


def test_im_connection_rejects_unsupported_platform() -> None:
    with pytest.raises(ValidationError):
        IMConnection(
            id="x", project_id="p", platform="wechat",  # not in Literal
            created_at=_now(), updated_at=_now(),
        )


def test_im_connection_rejects_unsupported_status() -> None:
    with pytest.raises(ValidationError):
        IMConnection(
            id="x", project_id="p", platform="feishu",
            status="banned",  # invalid
            created_at=_now(), updated_at=_now(),
        )


def test_im_connection_round_trip_json() -> None:
    c = IMConnection(
        id="conn-1", project_id="proj-1", platform="dingtalk",
        tenant_name="My Corp",
        auth_token_enc="abc123hex",
        consent_signed_by="admin-001",
        consent_user_id="emp-002",
        consent_signed_at=_now(),
        status="active",
        created_at=_now(), updated_at=_now(),
    )
    dump = c.model_dump_json()
    back = IMConnection.model_validate_json(dump)
    assert back.tenant_name == "My Corp"
    assert back.status == "active"
    assert back.auth_token_enc == "abc123hex"


def test_im_message_construct_with_mentions() -> None:
    msg = IMMessage(
        id="msg-1",
        connection_id="conn-1",
        platform_chat_id="chat-x",
        platform_msg_id="raw-456",
        sender=IMUser(user_id="u1", name="Alice"),
        content="@bob 这个 PR 要不要合?",
        mentions=["u2"],
        is_signal=True,
        received_at=_now(),
    )
    assert msg.is_signal is True
    assert msg.mentions == ["u2"]
    assert msg.redacted is False


def test_im_message_retention_optional() -> None:
    """retention_until 可空 (sync 时根据策略计算)."""
    msg = IMMessage(
        id="m", connection_id="c", platform_chat_id="ch",
        platform_msg_id="raw", content="x", received_at=_now(),
    )
    assert msg.retention_until is None


def test_value_segment_source_im_chat_mode() -> None:
    src = ValueSegmentSource(
        type="im_chat",
        mode="assistant",
        im_chat_id="chat-x",
        im_message_ids=["msg-1", "msg-2"],
        contributors=[IMUser(user_id="u1", name="Alice")],
    )
    assert src.mode == "assistant"
    assert src.contributors[0].name == "Alice"


def test_value_segment_source_event_no_mode() -> None:
    """type=event 时 mode/im_* 都可空, 复用 MVP 现有流水线."""
    src = ValueSegmentSource(type="event", event_id="evt-1")
    assert src.mode is None
    assert src.im_chat_id is None
    assert src.im_message_ids == []


def test_value_segment_rejects_bad_trust() -> None:
    with pytest.raises(ValidationError):
        ValueSegment(
            id="s", project_id="p",
            source=ValueSegmentSource(type="event"),
            content="x",
            trust_score=1.5,  # > 1
            extracted_at=_now(),
        )


def test_value_segment_round_trip() -> None:
    src = ValueSegmentSource(
        type="im_thread", mode="archive",
        im_chat_id="chat-1", im_message_ids=["m1"],
    )
    seg = ValueSegment(
        id="seg-1", project_id="p1",
        source=src,
        content="脱敏后的价值文本",
        trust_score=0.8,
        extracted_at=_now(),
    )
    back = ValueSegment.model_validate_json(seg.model_dump_json())
    assert back.source.type == "im_thread"
    assert back.source.mode == "archive"


# ─── Persistence ────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    return s


# ── im_connections ──


def test_upsert_im_connection_insert(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="pending", updated_at="2026-05-22T10:00:00Z",
        json_str=json.dumps({"id": "c1", "platform": "feishu"}),
    )
    items = store.list_im_connections("p1")
    assert len(items) == 1
    assert items[0]["platform"] == "feishu"


def test_upsert_im_connection_update_on_conflict(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="pending", updated_at="t1", json_str='{"v":1}',
    )
    store.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t2", json_str='{"v":2}',
    )
    got = store.get_im_connection("c1")
    assert got == {"v": 2}


def test_list_im_connections_filter_status(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="pending", updated_at="t1", json_str='{"id":"c1"}',
    )
    store.upsert_im_connection(
        connection_id="c2", project_id="p1", platform="dingtalk",
        status="active", updated_at="t2", json_str='{"id":"c2"}',
    )
    actives = store.list_im_connections("p1", status="active")
    assert [c["id"] for c in actives] == ["c2"]


def test_list_im_connections_isolated_by_project(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="A", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    store.upsert_im_connection(
        connection_id="c2", project_id="B", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c2"}',
    )
    assert [c["id"] for c in store.list_im_connections("A")] == ["c1"]
    assert [c["id"] for c in store.list_im_connections("B")] == ["c2"]


def test_get_im_connection_none_missing(store: SqliteStore) -> None:
    assert store.get_im_connection("ghost") is None


def test_delete_im_connection_cascades_to_messages(store: SqliteStore) -> None:
    """删 connection 时, im_messages.FK CASCADE 应级联."""
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    store.insert_im_message(
        message_id="m1", connection_id="c1",
        platform_chat_id="chat-1", platform_msg_id="raw-1",
        received_at="2026-05-22T10:00:00Z",
        retention_until="2026-08-20T10:00:00Z",
        is_signal=False, redacted=False,
        json_str=json.dumps({"id": "m1", "content": "x"}),
    )
    assert store.delete_im_connection("c1") is True
    assert store.list_im_messages("c1") == []


# ── im_messages ──


def test_insert_im_message_idempotent(store: SqliteStore) -> None:
    """同 (connection_id, platform_msg_id) 重复插入 → 第二次返 False."""
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    ok1 = store.insert_im_message(
        message_id="m1", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="raw-1", received_at="2026-05-22T10:00:00Z",
        retention_until=None, is_signal=False, redacted=False,
        json_str='{"id":"m1"}',
    )
    ok2 = store.insert_im_message(
        message_id="m1-other", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="raw-1",   # 同 raw msg id → IGNORE
        received_at="2026-05-22T10:01:00Z",
        retention_until=None, is_signal=False, redacted=False,
        json_str='{"id":"m1-other"}',
    )
    assert ok1 is True
    assert ok2 is False
    msgs = store.list_im_messages("c1")
    assert len(msgs) == 1
    assert msgs[0]["id"] == "m1"


def test_list_im_messages_filter_by_chat(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    for i, chat in enumerate(["chat-A", "chat-B", "chat-A"]):
        store.insert_im_message(
            message_id=f"m{i}", connection_id="c1",
            platform_chat_id=chat, platform_msg_id=f"raw-{i}",
            received_at=f"2026-05-22T10:0{i}:00Z",
            retention_until=None, is_signal=False, redacted=False,
            json_str=json.dumps({"id": f"m{i}"}),
        )
    a = store.list_im_messages("c1", chat_id="chat-A")
    assert {m["id"] for m in a} == {"m0", "m2"}


def test_list_im_messages_signal_only(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    store.insert_im_message(
        message_id="m1", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r1", received_at="2026-05-22T10:00:00Z",
        retention_until=None, is_signal=True, redacted=False,
        json_str=json.dumps({"id": "m1"}),
    )
    store.insert_im_message(
        message_id="m2", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r2", received_at="2026-05-22T10:01:00Z",
        retention_until=None, is_signal=False, redacted=False,
        json_str=json.dumps({"id": "m2"}),
    )
    signals = store.list_im_messages("c1", signal_only=True)
    assert [m["id"] for m in signals] == ["m1"]


def test_expire_im_messages_returns_ids_past_cutoff(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    old = "2026-01-01T00:00:00Z"
    new = "2026-05-22T10:00:00Z"
    store.insert_im_message(
        message_id="m-old", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r-old", received_at="2025-10-01T00:00:00Z",
        retention_until=old, is_signal=False, redacted=False,
        json_str=json.dumps({"id": "m-old"}),
    )
    store.insert_im_message(
        message_id="m-new", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r-new", received_at="2026-05-22T00:00:00Z",
        retention_until=new, is_signal=False, redacted=False,
        json_str=json.dumps({"id": "m-new"}),
    )
    cutoff = "2026-03-01T00:00:00Z"
    ids = store.expire_im_messages(cutoff)
    assert ids == ["m-old"]


def test_expire_im_messages_skips_already_redacted(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    store.insert_im_message(
        message_id="m-old", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r-old", received_at="2025-01-01T00:00:00Z",
        retention_until="2025-04-01T00:00:00Z",
        is_signal=False, redacted=True,  # 已脱敏 → 跳过
        json_str=json.dumps({"id": "m-old"}),
    )
    ids = store.expire_im_messages("2026-05-22T00:00:00Z")
    assert ids == []


def test_mark_im_message_redacted_updates_json(store: SqliteStore) -> None:
    store.upsert_im_connection(
        connection_id="c1", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    store.insert_im_message(
        message_id="m1", connection_id="c1", platform_chat_id="ch",
        platform_msg_id="r1", received_at="2026-05-22T10:00:00Z",
        retention_until="2026-08-20T10:00:00Z",
        is_signal=False, redacted=False,
        json_str=json.dumps({"id": "m1", "content": "原文"}),
    )
    new_json = json.dumps({"id": "m1", "content": "[已脱敏]"})
    ok = store.mark_im_message_redacted("m1", new_json)
    assert ok is True
    msgs = store.list_im_messages("c1")
    assert msgs[0]["content"] == "[已脱敏]"


# ── value_segments ──


def test_upsert_value_segment_basic(store: SqliteStore) -> None:
    store.upsert_value_segment(
        segment_id="s1", project_id="p1", source_type="im_chat",
        trust_score=0.7, extracted_at="2026-05-22T10:00:00Z",
        json_str=json.dumps({"id": "s1", "content": "x"}),
    )
    items = store.list_value_segments("p1")
    assert len(items) == 1
    assert items[0]["id"] == "s1"


def test_list_value_segments_sorted_by_trust_desc(store: SqliteStore) -> None:
    for (sid, trust) in [("low", 0.2), ("high", 0.9), ("mid", 0.5)]:
        store.upsert_value_segment(
            segment_id=sid, project_id="p", source_type="event",
            trust_score=trust, extracted_at="t",
            json_str=json.dumps({"id": sid}),
        )
    items = store.list_value_segments("p")
    assert [s["id"] for s in items] == ["high", "mid", "low"]


def test_list_value_segments_filter_by_source(store: SqliteStore) -> None:
    store.upsert_value_segment(
        segment_id="ev1", project_id="p", source_type="event",
        trust_score=0.5, extracted_at="t",
        json_str=json.dumps({"id": "ev1"}),
    )
    store.upsert_value_segment(
        segment_id="im1", project_id="p", source_type="im_chat",
        trust_score=0.5, extracted_at="t",
        json_str=json.dumps({"id": "im1"}),
    )
    im_only = store.list_value_segments("p", source_type="im_chat")
    assert [s["id"] for s in im_only] == ["im1"]


def test_list_value_segments_min_trust_filter(store: SqliteStore) -> None:
    for (sid, trust) in [("low", 0.2), ("high", 0.9)]:
        store.upsert_value_segment(
            segment_id=sid, project_id="p", source_type="event",
            trust_score=trust, extracted_at="t",
            json_str=json.dumps({"id": sid}),
        )
    out = store.list_value_segments("p", min_trust=0.5)
    assert [s["id"] for s in out] == ["high"]


def test_delete_value_segment(store: SqliteStore) -> None:
    store.upsert_value_segment(
        segment_id="s1", project_id="p", source_type="event",
        trust_score=0.5, extracted_at="t", json_str='{"id":"s1"}',
    )
    assert store.delete_value_segment("s1") is True
    assert store.list_value_segments("p") == []


def test_stats_includes_im_tables(store: SqliteStore) -> None:
    stats = store.stats()
    assert "im_connections" in stats
    assert "im_messages" in stats
    assert "value_segments" in stats
    assert stats["im_connections"] == 0


def test_idempotent_bootstrap_on_existing_db(tmp_path: Path) -> None:
    """老 DB 再次 bootstrap 不应报错; 新加的 3 张表都是 IF NOT EXISTS."""
    db_path = tmp_path / "state.sqlite"
    s1 = SqliteStore(db_path)
    s1._apply_schema()
    s2 = SqliteStore(db_path)
    s2._apply_schema()
    # 仍可写
    s2.upsert_im_connection(
        connection_id="c", project_id="p", platform="feishu",
        status="active", updated_at="t", json_str="{}",
    )
    assert s2.stats()["im_connections"] == 1
