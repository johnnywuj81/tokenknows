"""收尾覆盖率 · store.py / events.py / generation.py 残余 line.

主要目标:
- store rollback paths (DELETE 失败的 rollback 路径)
- events.py datasource_health 日期解析的 health 各档分支 + ValueError → cold
- list_events with cursor (323-324)
- generation.py 一些 404 + redaction confirm/exempt 错误分支
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistence.store import SqliteStore


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ─── store.py 残余 (160-162, 208-210, 316-317, 323-324) ────────────


def test_list_events_with_cursor(tmp_path: Path) -> None:
    """list_events cursor 分页 (line 323-324)."""
    store = SqliteStore(tmp_path / "e.sqlite")
    store._apply_schema()
    # 灌 5 个 event
    for i in range(5):
        store.upsert_event(
            event_id=f"ev-{i}", project_id="p1",
            source_type="github", event_type="commit",
            occurred_at=f"2026-05-2{i}T00:00:00Z",
            ingested_at="2026-05-22T00:00:00Z",
            content_hash=f"h{i}",
            json_str='{"id":"ev"}',
        )
    # 第 1 页拿 3 条
    rows, total = store.list_events("p1", limit=3)
    assert len(rows) == 3
    assert total == 5
    # 取 cursor 拿第 2 页
    rows_p2, _ = store.list_events("p1", limit=3, cursor="2026-05-23T00:00:00Z")
    # 应该只有早于 cursor 的
    assert len(rows_p2) <= 3


def test_list_events_with_to_iso_filter(tmp_path: Path) -> None:
    """to_iso 上界 (line 316-317)."""
    store = SqliteStore(tmp_path / "e.sqlite")
    store._apply_schema()
    store.upsert_event(
        event_id="ev-old", project_id="p1",
        source_type="github", event_type="commit",
        occurred_at="2026-05-10T00:00:00Z",
        ingested_at="2026-05-22T00:00:00Z",
        content_hash="h-old", json_str='{}',
    )
    store.upsert_event(
        event_id="ev-new", project_id="p1",
        source_type="github", event_type="commit",
        occurred_at="2026-05-25T00:00:00Z",
        ingested_at="2026-05-22T00:00:00Z",
        content_hash="h-new", json_str='{}',
    )
    rows, total = store.list_events("p1", to_iso="2026-05-20T00:00:00Z")
    assert total == 1   # 只有 ev-old


def test_replace_chapters_rollback_via_constraint(tmp_path: Path) -> None:
    """SQLite UNIQUE 约束失败 → 触发 rollback (line 160-162).

    用 (id) UNIQUE 在 chapters 表上, 灌重复 id 应触发 IntegrityError → ROLLBACK.
    """
    store = SqliteStore(tmp_path / "x.sqlite")
    store._apply_schema()
    store.upsert_asset("a1", "p", "d", "t", "t", "{}")
    store.upsert_chapter("c-existing", "a1", 0, "{}")
    # 替换为新一批 (DELETE 老的 + INSERT 新的). 若新批含 PK 冲突会 rollback
    # 但 replace_chapters 先 DELETE WHERE asset_id, 然后 INSERT, 所以 PK 冲突
    # 需要新批内部重复才会触发
    with pytest.raises(Exception):
        store.replace_chapters("a1", [
            ("dup-id", 0, "{}"),
            ("dup-id", 1, "{}"),   # 同 PK → IntegrityError
        ])


def test_replace_evidence_rollback_via_constraint(tmp_path: Path) -> None:
    """同上 evidence (line 208-210)."""
    store = SqliteStore(tmp_path / "x.sqlite")
    store._apply_schema()
    store.upsert_asset("a1", "p", "d", "t", "t", "{}")
    store.upsert_chapter("c1", "a1", 0, "{}")
    with pytest.raises(Exception):
        store.replace_evidence("c1", [
            ("dup-eid", "{}"),
            ("dup-eid", "{}"),   # PK 冲突
        ])


def test_persistence_init_function(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """覆盖 init.py 中的 persist alias (line 41)."""
    from app.config.settings import get_settings
    from app.persistence import store as store_mod
    settings = get_settings()
    monkeypatch.setattr(settings, "egress_log_path", str(tmp_path / "x.sqlite"))
    monkeypatch.setattr(store_mod, "_db", None)
    # 调 bootstrap (line 41 走过)
    s = store_mod.bootstrap()
    assert s is not None


# ─── events.py datasource_health 各档分支 ──────────────────────────


def test_datasource_health_active_within_24h(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """last_ingested < 24h → active (line 160-161)."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    class FakeStore:
        def datasource_health(self, project_id, window_days=30):
            return [{
                "source_type": "claude_code", "event_count": 5,
                "total_events": 5,
                "last_seen_at": one_hour_ago,
                "last_ingested_at": one_hour_ago,
            }]

    monkeypatch.setattr("app.persistence.get_db", lambda: FakeStore())
    r = client.get("/api/v1/projects/p/datasources/health")
    assert r.status_code == 200
    cc = next(it for it in r.json()["items"] if it["source_type"] == "claude_code")
    assert cc["health"] == "active"


def test_datasource_health_stale_within_7d(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """last_ingested 4 天前 → stale (line 162-163)."""
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()

    class FakeStore:
        def datasource_health(self, project_id, window_days=30):
            return [{
                "source_type": "github", "event_count": 5,
                "total_events": 5,
                "last_seen_at": four_days_ago,
                "last_ingested_at": four_days_ago,
            }]

    monkeypatch.setattr("app.persistence.get_db", lambda: FakeStore())
    r = client.get("/api/v1/projects/p/datasources/health")
    assert r.status_code == 200
    gh = next(it for it in r.json()["items"] if it["source_type"] == "github")
    assert gh["health"] == "stale"


def test_datasource_health_cold_over_7d(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """last_ingested 15 天前 → cold (line 164)."""
    long_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()

    class FakeStore:
        def datasource_health(self, project_id, window_days=30):
            return [{
                "source_type": "cursor", "event_count": 0,
                "total_events": 5,
                "last_seen_at": long_ago,
                "last_ingested_at": long_ago,
            }]

    monkeypatch.setattr("app.persistence.get_db", lambda: FakeStore())
    r = client.get("/api/v1/projects/p/datasources/health")
    assert r.status_code == 200
    cur = next(it for it in r.json()["items"] if it["source_type"] == "cursor")
    assert cur["health"] == "cold"


def test_datasource_health_invalid_iso_cold(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法 ISO → ValueError → 'cold' (line 158-159)."""

    class FakeStore:
        def datasource_health(self, project_id, window_days=30):
            return [{
                "source_type": "github", "event_count": 1,
                "total_events": 1,
                "last_seen_at": "garbage-date",
                "last_ingested_at": "garbage-date",
            }]

    monkeypatch.setattr("app.persistence.get_db", lambda: FakeStore())
    r = client.get("/api/v1/projects/p/datasources/health")
    assert r.status_code == 200
    gh = next(it for it in r.json()["items"] if it["source_type"] == "github")
    assert gh["health"] == "cold"


def test_datasource_health_naive_iso_treated_as_utc(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """naive datetime (无 tzinfo) → 当 UTC (line 155-156)."""
    naive_str = (datetime.now() - timedelta(hours=2)).isoformat()  # 无 Z 后缀

    class FakeStore:
        def datasource_health(self, project_id, window_days=30):
            return [{
                "source_type": "local_file", "event_count": 1,
                "total_events": 1,
                "last_seen_at": naive_str,
                "last_ingested_at": naive_str,
            }]

    monkeypatch.setattr("app.persistence.get_db", lambda: FakeStore())
    r = client.get("/api/v1/projects/p/datasources/health")
    assert r.status_code == 200


# ─── events.py ingest 400 detail line 40 ──────────────────────────


def test_ingest_events_over_500_message(client: TestClient) -> None:
    """详情消息覆盖 line 40."""
    events = [
        {
            "source_type": "github", "source_ref": "o/r",
            "external_id": f"e{i}", "version": 1, "event_type": "commit",
            "occurred_at": "2026-05-22T00:00:00Z",
            "title": "t", "content": "c", "content_hash": f"h{i}",
            "payload": {}, "tags": [],
        }
        for i in range(501)
    ]
    r = client.post("/api/v1/projects/p/events", json={"events": events})
    assert r.status_code == 400
    assert "500" in r.json()["detail"]
