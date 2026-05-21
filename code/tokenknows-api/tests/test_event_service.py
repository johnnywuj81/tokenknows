"""event_service · ingest_events / list_events / get_event 单测.

用 monkeypatch 隔离 SQLite 让 tests 跑快+独立.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.schemas.event import EventCreate
from app.services import event_service


def _make_event(content_hash: str = "h1", title: str = "t") -> EventCreate:
    return EventCreate(
        source_type="github",
        source_ref="o/r",
        external_id=f"ext-{content_hash}",
        version=1,
        event_type="commit",
        occurred_at=datetime.now(timezone.utc),
        title=title,
        content=f"content for {title}",
        content_hash=content_hash,
        payload={},
        tags=[],
    )


class FakeDb:
    """轻量替身 DB - 用 set 模拟 content_hash 唯一索引."""

    def __init__(self) -> None:
        self.events_by_id: dict[str, dict] = {}
        self.hashes: set[str] = set()

    def upsert_event(
        self,
        event_id: str,
        project_id: str,
        source_type: str,
        event_type: str,
        occurred_at: str,
        ingested_at: str,
        content_hash: str,
        json_str: str,
    ) -> bool:
        key = f"{project_id}:{content_hash}"
        if key in self.hashes:
            return False
        self.hashes.add(key)
        import json as _json
        self.events_by_id[event_id] = _json.loads(json_str)
        return True

    def list_events(
        self,
        project_id: str,
        source_type: str | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        rows = [e for e in self.events_by_id.values() if e.get("project_id") == project_id]
        if source_type:
            rows = [e for e in rows if e.get("source_type") == source_type]
        rows = sorted(rows, key=lambda e: e["occurred_at"], reverse=True)
        return rows[:limit], len(rows)

    def get_event(self, event_id: str) -> dict | None:
        return self.events_by_id.get(event_id)


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDb:
    """monkeypatch get_db → FakeDb."""
    db = FakeDb()
    monkeypatch.setattr(event_service, "get_db", lambda: db)
    return db


# ─── ingest_events ──────────────────────────────────────────────────


def test_ingest_single_event(fake_db: FakeDb) -> None:
    resp = event_service.ingest_events("proj-A", [_make_event("h1")])
    assert resp.ingested == 1
    assert resp.skipped == 0
    assert len(resp.event_ids) == 1
    assert resp.event_ids[0].startswith("evt-")


def test_ingest_dedup_by_content_hash(fake_db: FakeDb) -> None:
    """同 content_hash 第二次 → skipped."""
    event_service.ingest_events("proj-A", [_make_event("dup", "t1")])
    resp = event_service.ingest_events("proj-A", [_make_event("dup", "t2")])
    assert resp.ingested == 0
    assert resp.skipped == 1


def test_ingest_different_projects_no_dedup(fake_db: FakeDb) -> None:
    """同 content_hash 但不同 project → 都收 (隔离)."""
    event_service.ingest_events("proj-A", [_make_event("shared")])
    resp = event_service.ingest_events("proj-B", [_make_event("shared")])
    assert resp.ingested == 1
    assert resp.skipped == 0


def test_ingest_batch_mixed(fake_db: FakeDb) -> None:
    """5 个事件, 3 新 2 dup → ingested=3 skipped=2."""
    # 先灌 2 个
    event_service.ingest_events("proj-A", [_make_event("a"), _make_event("b")])
    # 再批量灌 5 个 (2 重复 + 3 新)
    batch = [
        _make_event("a"),  # dup
        _make_event("b"),  # dup
        _make_event("c"),
        _make_event("d"),
        _make_event("e"),
    ]
    resp = event_service.ingest_events("proj-A", batch)
    assert resp.ingested == 3
    assert resp.skipped == 2


# ─── list_events ────────────────────────────────────────────────────


def test_list_events_empty_project(fake_db: FakeDb) -> None:
    events, meta = event_service.list_events("proj-empty")
    assert events == []
    assert meta["total"] == 0
    assert meta["has_more"] is False


def test_list_events_returns_meta(fake_db: FakeDb) -> None:
    event_service.ingest_events(
        "proj-A",
        [_make_event(f"h{i}") for i in range(3)],
    )
    events, meta = event_service.list_events("proj-A")
    assert len(events) == 3
    assert meta["total"] == 3


def test_list_events_limit_triggers_has_more(fake_db: FakeDb) -> None:
    """limit == 返回数 → has_more=True (可能还有下一页)."""
    event_service.ingest_events(
        "proj-A",
        [_make_event(f"h{i}") for i in range(10)],
    )
    events, meta = event_service.list_events("proj-A", limit=5)
    assert len(events) == 5
    assert meta["has_more"] is True
    assert meta["cursor"] is not None


def test_list_events_filter_by_source_type(fake_db: FakeDb) -> None:
    """source_type filter 透传到 db.list_events."""
    event_service.ingest_events("proj-A", [_make_event("gh1")])
    # 别的 source_type 也灌一条
    other = _make_event("cc1")
    other.source_type = "claude_code"
    event_service.ingest_events("proj-A", [other])

    events, _ = event_service.list_events("proj-A", source_type="github")
    assert all(e.source_type == "github" for e in events)


# ─── get_event ──────────────────────────────────────────────────────


def test_get_event_returns_none_for_missing(fake_db: FakeDb) -> None:
    assert event_service.get_event("evt-not-real") is None


def test_get_event_returns_event_after_ingest(fake_db: FakeDb) -> None:
    resp = event_service.ingest_events("proj-A", [_make_event("h1")])
    ev_id = resp.event_ids[0]
    found = event_service.get_event(ev_id)
    assert found is not None
    assert found.id == ev_id
