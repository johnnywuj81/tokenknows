"""T131 · event_value_segment_service 单测 + 与 event_service.ingest_events 集成."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.event import Event, EventAuthor, EventCreate
from app.services import event_service, event_value_segment_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mk_event(
    *,
    event_id: str = "evt-test1",
    project_id: str = "p1",
    content: str = "本周完成了 PR 关键决策, 长内容长内容长内容.",
    trust_score: float | None = 0.8,
    source_type: str = "claude_code",
) -> Event:
    return Event(
        id=event_id,
        project_id=project_id,
        source_type=source_type,
        source_ref="ref-1",
        external_id="ext-1",
        version=1,
        event_type="ai_conversation_turn",
        occurred_at=_now(),
        ingested_at=_now(),
        author=EventAuthor(name="alice"),
        title="title",
        content=content,
        payload={},
        content_hash="hash-" + event_id,
        trust_score=trust_score,
    )


def _mk_event_create(
    *,
    content: str = "本周完成了关键架构决策长内容长内容长内容.",
    trust_score: float | None = 0.8,
    external_id: str = "ext-1",
) -> EventCreate:
    return EventCreate(
        source_type="claude_code",
        source_ref="ref-1",
        external_id=external_id,
        event_type="ai_conversation_turn",
        occurred_at=_now(),
        author=EventAuthor(name="alice"),
        title="title",
        content=content,
        content_hash="hash-" + external_id,
        trust_score=trust_score,
    )


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


# ── 过滤规则 (纯函数) ───────────────────────────────────────────


def test_event_to_segment_happy_path():
    ev = _mk_event(content="x" * 50, trust_score=0.7)
    seg = event_value_segment_service.event_to_segment(ev)
    assert seg is not None
    assert seg.id == "seg-evt-evt-test1"
    assert seg.source.type == "event"
    assert seg.source.event_id == "evt-test1"
    assert seg.trust_score == 0.7
    assert seg.content.startswith("x")


def test_event_to_segment_filters_low_trust():
    """trust < 0.3 → None."""
    ev = _mk_event(trust_score=0.1)
    assert event_value_segment_service.event_to_segment(ev) is None


def test_event_to_segment_filters_short_content():
    """content < 20 chars → None."""
    ev = _mk_event(content="短", trust_score=0.9)
    assert event_value_segment_service.event_to_segment(ev) is None


def test_event_to_segment_filters_whitespace_only():
    """全空白 content (strip 后 = '') → None."""
    ev = _mk_event(content="   \n\t   ", trust_score=0.9)
    assert event_value_segment_service.event_to_segment(ev) is None


def test_event_to_segment_default_trust_when_none():
    """trust_score=None → 视为 0.5 (默认), 内容达标即通过."""
    ev = _mk_event(trust_score=None, content="x" * 30)
    seg = event_value_segment_service.event_to_segment(ev)
    assert seg is not None
    assert seg.trust_score == 0.5


def test_event_to_segment_id_deterministic():
    """同一 event.id → 总是同一 segment.id (幂等)."""
    ev = _mk_event(event_id="evt-foo")
    s1 = event_value_segment_service.event_to_segment(ev)
    s2 = event_value_segment_service.event_to_segment(ev)
    assert s1 is not None and s2 is not None
    assert s1.id == s2.id == "seg-evt-evt-foo"


# ── 批量持久化 ───────────────────────────────────────────────


def test_process_events_persists_and_returns(fresh_db):
    events = [
        _mk_event(event_id=f"evt-{i}", content="x" * 50, trust_score=0.7)
        for i in range(3)
    ]
    written = event_value_segment_service.process_events_to_segments("p1", events)
    assert len(written) == 3
    # db 查得到
    rows = fresh_db.list_value_segments("p1", source_type="event")
    assert len(rows) == 3


def test_process_events_skips_filtered(fresh_db):
    """混入低 trust + 短内容 → 只写过滤通过的."""
    events = [
        _mk_event(event_id="evt-good", content="x" * 30, trust_score=0.8),
        _mk_event(event_id="evt-bad-trust", content="x" * 30, trust_score=0.1),
        _mk_event(event_id="evt-bad-content", content="hi", trust_score=0.9),
    ]
    written = event_value_segment_service.process_events_to_segments("p1", events)
    assert len(written) == 1
    assert written[0].source.event_id == "evt-good"
    rows = fresh_db.list_value_segments("p1", source_type="event")
    assert len(rows) == 1


def test_process_events_idempotent(fresh_db):
    """同 events 跑两次 → segments 不重复 (ON CONFLICT id 更新)."""
    events = [_mk_event(event_id="evt-x", content="x" * 30, trust_score=0.7)]
    event_value_segment_service.process_events_to_segments("p1", events)
    event_value_segment_service.process_events_to_segments("p1", events)
    rows = fresh_db.list_value_segments("p1", source_type="event")
    assert len(rows) == 1


def test_process_events_empty_input_returns_empty(fresh_db):
    assert event_value_segment_service.process_events_to_segments("p1", []) == []


# ── 集成: ingest_events → 自动提炼 ────────────────────────────


def test_ingest_events_triggers_value_segment_extraction(fresh_db):
    """T131 · ingest_events 完成后, value_segments 应同步出现."""
    payload = [
        _mk_event_create(external_id=f"ext-{i}", content="x" * 50, trust_score=0.8)
        for i in range(2)
    ]
    resp = event_service.ingest_events("p1", payload)
    assert resp.ingested == 2

    # value_segments 表应有 2 条 source_type='event' 记录
    rows = fresh_db.list_value_segments("p1", source_type="event")
    assert len(rows) == 2


def test_ingest_events_extraction_failure_doesnt_break_ingest(
    fresh_db, monkeypatch: pytest.MonkeyPatch,
):
    """提炼失败时 ingest_events 仍返回正常 ingested 计数."""
    def fake_raise(*a, **kw):
        raise RuntimeError("extraction boom")
    monkeypatch.setattr(
        "app.services.event_value_segment_service.process_events_to_segments",
        fake_raise,
    )
    payload = [_mk_event_create(external_id="ext-z", trust_score=0.8)]
    resp = event_service.ingest_events("p1", payload)
    assert resp.ingested == 1
    # value_segments 无数据 (提炼失败), 但 events 表有
    assert fresh_db.list_value_segments("p1", source_type="event") == []


def test_ingest_events_skipped_dup_not_re_extracted(fresh_db):
    """重复 content_hash 的 event 在 ingest 时被跳过, 不应触发新 segment."""
    payload = [_mk_event_create(external_id="dup-1", content="x" * 30, trust_score=0.7)]
    event_service.ingest_events("p1", payload)
    # 第二次同 hash → skipped
    resp2 = event_service.ingest_events("p1", payload)
    assert resp2.ingested == 0
    assert resp2.skipped == 1
    # segments 仍只 1 条
    rows = fresh_db.list_value_segments("p1", source_type="event")
    assert len(rows) == 1
