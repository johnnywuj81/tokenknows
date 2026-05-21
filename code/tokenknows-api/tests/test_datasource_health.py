"""SqliteStore.datasource_health 单测.

用 tmp_path 创建一个临时 DB, 用 upsert_event 灌真数据, 验证 SQL 聚合正确.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence.store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    """干净的临时 store, 已建表."""
    db_path = tmp_path / "test.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    return s


def _ingest(
    store: SqliteStore,
    *,
    project_id: str,
    source_type: str,
    occurred_at: str,
    ingested_at: str | None = None,
    event_id: str | None = None,
    content_hash: str | None = None,
) -> None:
    """灌一条 event 进去, 默认 ingested_at = occurred_at."""
    ev_id = event_id or f"ev-{source_type}-{occurred_at}"
    ch = content_hash or f"h-{ev_id}"
    payload = json.dumps({"source_type": source_type, "title": "t", "content": "c"})
    store.upsert_event(
        event_id=ev_id,
        project_id=project_id,
        source_type=source_type,
        event_type="ai_conversation_turn",
        occurred_at=occurred_at,
        ingested_at=ingested_at or occurred_at,
        content_hash=ch,
        json_str=payload,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt.tzinfo else dt.isoformat()


# ─── 基本聚合 ──────────────────────────────────────────────────────


def test_empty_project_returns_empty(store: SqliteStore) -> None:
    result = store.datasource_health("proj-empty", window_days=30)
    assert result == []


def test_single_source_aggregated(store: SqliteStore) -> None:
    now = datetime.now(timezone.utc)
    pid = "proj-1"
    _ingest(store, project_id=pid, source_type="claude_code",
            occurred_at=_iso(now - timedelta(hours=2)))
    _ingest(store, project_id=pid, source_type="claude_code",
            occurred_at=_iso(now - timedelta(hours=5)))

    result = store.datasource_health(pid, window_days=30)
    assert len(result) == 1
    r = result[0]
    assert r["source_type"] == "claude_code"
    assert r["event_count"] == 2
    assert r["total_events"] == 2
    assert r["last_seen_at"] is not None
    assert r["last_ingested_at"] is not None


def test_multi_source_returned_separately(store: SqliteStore) -> None:
    now = datetime.now(timezone.utc)
    pid = "proj-multi"
    _ingest(store, project_id=pid, source_type="claude_code",
            occurred_at=_iso(now - timedelta(hours=1)))
    _ingest(store, project_id=pid, source_type="github",
            occurred_at=_iso(now - timedelta(hours=2)))
    _ingest(store, project_id=pid, source_type="github",
            occurred_at=_iso(now - timedelta(hours=3)))
    _ingest(store, project_id=pid, source_type="local_file",
            occurred_at=_iso(now - timedelta(hours=4)))

    result = store.datasource_health(pid, window_days=30)
    assert len(result) == 3
    by_type = {r["source_type"]: r for r in result}
    assert by_type["claude_code"]["event_count"] == 1
    assert by_type["github"]["event_count"] == 2
    assert by_type["local_file"]["event_count"] == 1


# ─── window vs total 语义 ──────────────────────────────────────────


def test_window_excludes_old_but_total_includes(store: SqliteStore) -> None:
    """关键边界: cursor 8 个月前的 backfill — window 看不到, total 看得到."""
    now = datetime.now(timezone.utc)
    pid = "proj-backfill"
    old_when = _iso(now - timedelta(days=240))   # 8 个月前 occurred
    recent_ingest = _iso(now - timedelta(hours=1))  # 1h 前 ingested

    _ingest(
        store,
        project_id=pid,
        source_type="cursor",
        occurred_at=old_when,
        ingested_at=recent_ingest,
    )

    result = store.datasource_health(pid, window_days=30)
    assert len(result) == 1
    r = result[0]
    assert r["source_type"] == "cursor"
    assert r["event_count"] == 0      # 30 天窗口外
    assert r["total_events"] == 1     # 全量看得到
    # last_ingested_at 反映"插件还在跑"
    assert r["last_ingested_at"] is not None


def test_project_scoped(store: SqliteStore) -> None:
    """别的项目的事件不影响 (event_id/content_hash 必须唯一才能区分)."""
    now = datetime.now(timezone.utc)
    _ingest(store, project_id="proj-a", source_type="github",
            occurred_at=_iso(now - timedelta(hours=1)),
            event_id="ev-a-1", content_hash="ha-1")
    _ingest(store, project_id="proj-b", source_type="github",
            occurred_at=_iso(now - timedelta(hours=1)),
            event_id="ev-b-1", content_hash="hb-1")
    _ingest(store, project_id="proj-b", source_type="github",
            occurred_at=_iso(now - timedelta(hours=2)),
            event_id="ev-b-2", content_hash="hb-2")

    a = store.datasource_health("proj-a", window_days=30)
    b = store.datasource_health("proj-b", window_days=30)
    assert a[0]["event_count"] == 1
    assert b[0]["event_count"] == 2


def test_sorted_by_event_count_desc(store: SqliteStore) -> None:
    """返回顺序按窗口内 event_count 降序."""
    now = datetime.now(timezone.utc)
    pid = "proj-sort"
    for i in range(5):
        _ingest(store, project_id=pid, source_type="claude_code",
                occurred_at=_iso(now - timedelta(hours=i + 1)),
                event_id=f"cc-{i}", content_hash=f"hcc-{i}")
    for i in range(2):
        _ingest(store, project_id=pid, source_type="github",
                occurred_at=_iso(now - timedelta(hours=i + 1)),
                event_id=f"gh-{i}", content_hash=f"hgh-{i}")
    _ingest(store, project_id=pid, source_type="local_file",
            occurred_at=_iso(now - timedelta(hours=1)),
            event_id="lf-0", content_hash="hlf-0")

    result = store.datasource_health(pid, window_days=30)
    counts = [r["event_count"] for r in result]
    assert counts == sorted(counts, reverse=True)
    assert result[0]["source_type"] == "claude_code"   # 最多
    assert result[0]["event_count"] == 5


# ─── 时间字段精度 ──────────────────────────────────────────────────


def test_last_seen_is_max_of_all_occurred(store: SqliteStore) -> None:
    now = datetime.now(timezone.utc)
    pid = "proj-last-seen"
    times = [
        _iso(now - timedelta(hours=10)),
        _iso(now - timedelta(hours=1)),    # 最新
        _iso(now - timedelta(hours=5)),
    ]
    for i, t in enumerate(times):
        _ingest(store, project_id=pid, source_type="github",
                occurred_at=t, event_id=f"e-{i}", content_hash=f"h-{i}")

    result = store.datasource_health(pid, window_days=30)
    assert result[0]["last_seen_at"] == times[1]   # MAX


def test_window_filter_only_affects_event_count(store: SqliteStore) -> None:
    """window_days=1: 24h 外的不算 event_count, 但仍参与 total/last_seen."""
    now = datetime.now(timezone.utc)
    pid = "proj-window"
    _ingest(store, project_id=pid, source_type="github",
            occurred_at=_iso(now - timedelta(hours=2)),
            event_id="recent", content_hash="hr")
    _ingest(store, project_id=pid, source_type="github",
            occurred_at=_iso(now - timedelta(days=10)),
            event_id="old", content_hash="ho")

    r1 = store.datasource_health(pid, window_days=1)[0]
    assert r1["event_count"] == 1     # 只 recent 在 24h 内
    assert r1["total_events"] == 2    # 全部 2 条

    r2 = store.datasource_health(pid, window_days=30)[0]
    assert r2["event_count"] == 2     # 都在 30 天内
    assert r2["total_events"] == 2
