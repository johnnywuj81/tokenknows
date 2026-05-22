"""IM Retention + Revocation (v0.3 T22).

覆盖:
- compute_retention_until 默认 90 天
- expire_messages_now 把到期 + 未脱敏的消息 redacted=1
- expire_messages_now 跳过已脱敏的消息
- revoke_connection 标 status=revoked + revoked_at
- force_purge_revoked_connection 宽限期内 → skip
- force_purge_revoked_connection 宽限期后 → 全部 redact
- anonymize_user_segments 把 contributors 中的 user_id 替换为 anon-xxx
- upcoming_expirations 未来 N 天到期统计
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import settings as settings_module
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.im import IMUser, ValueSegment, ValueSegmentSource
from app.services import im_crypto, im_service
from app.services.im import retention


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    settings_module.get_settings().im_encryption_key = Fernet.generate_key().decode()
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── compute_retention_until ────────────────────────────────


def test_compute_retention_default_90_days() -> None:
    base = datetime(2026, 5, 22, tzinfo=timezone.utc)
    out = retention.compute_retention_until(base)
    assert out == base + timedelta(days=90)


def test_compute_retention_custom_days() -> None:
    base = datetime(2026, 5, 22, tzinfo=timezone.utc)
    out = retention.compute_retention_until(base, retention_days=30)
    assert out == base + timedelta(days=30)


# ─── expire_messages_now ────────────────────────────────────


def _seed_message(
    store: SqliteStore,
    message_id: str,
    connection_id: str = "c1",
    received_at: str = "2026-01-01T00:00:00+00:00",
    retention_until: str | None = None,
    redacted: bool = False,
    content: str = "原文消息",
) -> None:
    payload = {
        "id": message_id,
        "connection_id": connection_id,
        "platform_chat_id": "ch",
        "platform_msg_id": "raw-" + message_id,
        "sender": {"user_id": "u1", "name": "Alice"},
        "content": content,
        "mentions": [],
        "is_signal": False,
        "received_at": received_at,
        "retention_until": retention_until,
        "redacted": redacted,
    }
    store.insert_im_message(
        message_id=message_id,
        connection_id=connection_id,
        platform_chat_id="ch",
        platform_msg_id="raw-" + message_id,
        received_at=received_at,
        retention_until=retention_until,
        is_signal=False,
        redacted=redacted,
        json_str=json.dumps(payload, ensure_ascii=False),
    )


def test_expire_messages_no_due_returns_zero(fresh_state: SqliteStore) -> None:
    # seed connection 要先有, 否则 FK 报错
    fresh_state.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    _seed_message(
        fresh_state, "m1",
        retention_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )
    result = retention.expire_messages_now()
    assert result["scanned"] == 0
    assert result["redacted"] == 0


def test_expire_messages_redacts_due_messages(fresh_state: SqliteStore) -> None:
    fresh_state.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    # 1 条过期 + 1 条未来
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    _seed_message(fresh_state, "m1", retention_until=past, content="过期内容")
    _seed_message(fresh_state, "m2", retention_until=future, content="还在保留期")

    result = retention.expire_messages_now()
    assert result["scanned"] == 1
    assert result["redacted"] == 1

    # m1 已脱敏
    msgs = fresh_state.list_im_messages("c1")
    by_id = {m["id"]: m for m in msgs}
    assert by_id["m1"]["redacted"] is True
    assert by_id["m1"]["content"] == retention.REDACTED_PLACEHOLDER
    assert by_id["m2"]["redacted"] is False


def test_expire_messages_skips_already_redacted(fresh_state: SqliteStore) -> None:
    fresh_state.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    _seed_message(fresh_state, "m1", retention_until=past, redacted=True)
    result = retention.expire_messages_now()
    assert result["scanned"] == 0  # SQL where 已过滤


# ─── revoke / force_purge ─────────────────────────────────────


def test_revoke_connection_sets_status_and_revoked_at() -> None:
    conn = im_service.create_connection("p1", "feishu")
    updated = retention.revoke_connection(conn.id)
    assert updated is not None
    assert updated.status == "revoked"
    assert updated.revoked_at is not None


def test_revoke_missing_connection_returns_none() -> None:
    assert retention.revoke_connection("ghost") is None


def test_force_purge_within_grace_skips(fresh_state: SqliteStore) -> None:
    conn = im_service.create_connection("p1", "feishu")
    retention.revoke_connection(conn.id)
    _seed_message(fresh_state, "m1", connection_id=conn.id, content="orig")
    result = retention.force_purge_revoked_connection(conn.id)
    assert result["messages_redacted"] == 0


def test_force_purge_after_grace_redacts_all(fresh_state: SqliteStore) -> None:
    conn = im_service.create_connection("p1", "feishu")
    retention.revoke_connection(conn.id)
    _seed_message(fresh_state, "m1", connection_id=conn.id, content="orig-1")
    _seed_message(fresh_state, "m2", connection_id=conn.id, content="orig-2")
    # 模拟宽限期过去
    future = datetime.now(timezone.utc) + timedelta(days=31)
    result = retention.force_purge_revoked_connection(conn.id, now=future)
    assert result["messages_redacted"] == 2
    assert result["messages_total"] == 2
    msgs = fresh_state.list_im_messages(conn.id)
    for m in msgs:
        assert m["redacted"] is True
        assert m["content"] == retention.REDACTED_PLACEHOLDER


def test_force_purge_active_connection_no_op(fresh_state: SqliteStore) -> None:
    """status != revoked 的不做 purge."""
    conn = im_service.create_connection("p1", "feishu")
    _seed_message(fresh_state, "m1", connection_id=conn.id, content="x")
    result = retention.force_purge_revoked_connection(conn.id)
    assert result["messages_redacted"] == 0


# ─── anonymize_user_segments ─────────────────────────────────


def test_anonymize_user_replaces_contributors(fresh_state: SqliteStore) -> None:
    seg = ValueSegment(
        id="seg-1", project_id="p1",
        source=ValueSegmentSource(
            type="im_thread",
            mode="assistant",
            im_chat_id="ch",
            im_message_ids=["m1", "m2"],
            contributors=[
                IMUser(user_id="u-target", name="TargetUser", email="t@x.com"),
                IMUser(user_id="u-other", name="OtherUser"),
            ],
        ),
        content="x" * 60,
        trust_score=0.7,
        extracted_at=_now(),
    )
    fresh_state.upsert_value_segment(
        segment_id=seg.id, project_id=seg.project_id,
        source_type=seg.source.type, trust_score=seg.trust_score,
        extracted_at=seg.extracted_at.isoformat(),
        json_str=seg.model_dump_json(),
    )
    n = retention.anonymize_user_segments("p1", "u-target")
    assert n == 1
    after = fresh_state.list_value_segments("p1")
    contribs = after[0]["source"]["contributors"]
    target = [c for c in contribs if c["name"] == "anonymous"]
    other = [c for c in contribs if c["name"] == "OtherUser"]
    assert len(target) == 1
    assert target[0]["user_id"].startswith("anon-")
    assert target[0].get("email") is None
    # 其它用户不变
    assert len(other) == 1


def test_anonymize_user_not_in_any_segment_returns_zero(fresh_state: SqliteStore) -> None:
    n = retention.anonymize_user_segments("p1", "ghost")
    assert n == 0


# ─── upcoming_expirations ────────────────────────────────────


def test_upcoming_expirations_groups_by_connection(fresh_state: SqliteStore) -> None:
    fresh_state.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    fresh_state.upsert_im_connection(
        connection_id="c2", project_id="p1", platform="dingtalk",
        status="active", updated_at="t", json_str='{"id":"c2"}',
    )
    # c1: 2 条将在 3 天后到期
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    _seed_message(fresh_state, "m1", connection_id="c1", retention_until=soon)
    _seed_message(fresh_state, "m2", connection_id="c1", retention_until=soon)
    # c2: 1 条将在 100 天后到期 (超出窗口)
    far = (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()
    _seed_message(fresh_state, "m3", connection_id="c2", retention_until=far)

    out = retention.upcoming_expirations(days_ahead=7)
    out_by_id = {row["connection_id"]: row for row in out}
    assert "c1" in out_by_id
    assert out_by_id["c1"]["count"] == 2
    # c2 不在 7 天窗口里
    assert "c2" not in out_by_id


def test_upcoming_expirations_excludes_redacted(fresh_state: SqliteStore) -> None:
    fresh_state.upsert_im_connection(
        connection_id="c1", project_id="p1", platform="feishu",
        status="active", updated_at="t", json_str='{"id":"c1"}',
    )
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    _seed_message(
        fresh_state, "m1", connection_id="c1",
        retention_until=soon, redacted=True,  # 已脱敏
    )
    out = retention.upcoming_expirations(days_ahead=7)
    assert out == []


# ─── 边界 ────────────────────────────────────────────────────


def test_redact_message_dict_preserves_metadata() -> None:
    raw = {
        "id": "m1",
        "connection_id": "c1",
        "sender": {"user_id": "u1", "name": "Alice"},
        "content": "敏感原文",
        "mentions": ["u2"],
        "redacted": False,
    }
    out_json = retention._redact_message_dict(raw)
    out = json.loads(out_json)
    assert out["content"] == retention.REDACTED_PLACEHOLDER
    assert out["redacted"] is True
    assert out["sender"]["name"] == "Alice"  # 保留发送者元数据
