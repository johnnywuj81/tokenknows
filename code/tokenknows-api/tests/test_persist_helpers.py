"""_persist_asset / _persist_redaction_job / _persist_publish_record / _bootstrap_from_db.

用真 SQLite tmp DB 跑端到端持久化往返.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.persistence.store import SqliteStore
from app.schemas.asset import (
    Asset,
    Chapter,
    Evidence,
    EvidencePreview,
    PublishRecord,
    RedactionScanJob,
)
from app.services import generation_service as gen


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SqliteStore:
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(gen, "get_db", lambda: s)
    yield s


@pytest.fixture(autouse=True)
def isolate():
    snap_a = dict(gen._assets)
    snap_c = dict(gen._chapters)
    snap_e = dict(gen._evidence_by_chapter)
    snap_p = dict(gen._progress)
    snap_pub = dict(gen._publish_records)
    snap_red = dict(gen._redaction_jobs)
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._publish_records.clear()
    gen._redaction_jobs.clear()
    yield
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._publish_records.clear()
    gen._redaction_jobs.clear()
    gen._assets.update(snap_a)
    gen._chapters.update(snap_c)
    gen._evidence_by_chapter.update(snap_e)
    gen._progress.update(snap_p)
    gen._publish_records.update(snap_pub)
    gen._redaction_jobs.update(snap_red)


def _make_asset(asset_id: str = "a1") -> Asset:
    return Asset(
        id=asset_id, project_id="p1", type="weekly_report",
        title="t", status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )


def _make_chapter(idx: int, asset_id: str = "a1") -> Chapter:
    return Chapter(
        id=f"ch-{idx}", asset_id=asset_id, order_index=idx,
        title=f"§{idx}", content=f"content {idx}",
    )


# ─── _persist_asset (端到端 round-trip) ──────────────────────────


def test_persist_asset_writes_asset_row(store: SqliteStore) -> None:
    a = _make_asset("a1")
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._persist_asset("a1")
    rows = store.load_all_assets()
    assert len(rows) == 1
    assert rows[0]["id"] == "a1"


def test_persist_asset_missing_no_op(store: SqliteStore) -> None:
    """asset_id 不在 _assets → 不抛."""
    gen._persist_asset("a-fake")   # no-op, 不抛
    assert store.load_all_assets() == []


def test_persist_asset_writes_chapters(store: SqliteStore) -> None:
    a = _make_asset("a1")
    chs = [_make_chapter(0), _make_chapter(1)]
    gen._assets["a1"] = a
    gen._chapters["a1"] = chs
    gen._persist_asset("a1")
    loaded = store.load_chapters_for_asset("a1")
    assert len(loaded) == 2


def test_persist_asset_writes_progress(store: SqliteStore) -> None:
    a = _make_asset("a1")
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._progress["a1"] = gen._initial_progress("a1")
    gen._persist_asset("a1")
    loaded = store.load_progress("a1")
    assert loaded is not None
    assert loaded["asset_id"] == "a1"


def test_persist_asset_writes_evidence(store: SqliteStore) -> None:
    a = _make_asset("a1")
    ch = _make_chapter(0)
    gen._assets["a1"] = a
    gen._chapters["a1"] = [ch]
    gen._evidence_by_chapter[ch.id] = [
        Evidence(
            id="e1", chapter_id=ch.id, event_id="ev1",
            event_version=1, span_start=0, span_end=10,
            citation_text="x", manually_added=False, stale=False,
            event_preview=EvidencePreview(
                event_id="ev1", source_type="github",
                source_ref="o/r", occurred_at=_now().isoformat(),
                content_excerpt="x",
            ),
        ),
    ]
    gen._persist_asset("a1")
    loaded = store.load_evidence_for_chapter(ch.id)
    assert len(loaded) == 1


# ─── _persist_redaction_job ────────────────────────────────────────


def test_persist_redaction_job_writes(store: SqliteStore) -> None:
    a = _make_asset("a1")
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._persist_asset("a1")   # 先建 asset
    gen._redaction_jobs["a1"] = RedactionScanJob(
        job_id="job-1", asset_id="a1", status="done",
        progress=1.0, items=[],
    )
    gen._persist_redaction_job("a1")
    jobs = store.load_all_redaction_jobs()
    assert "a1" in jobs


def test_persist_redaction_job_missing_no_op(store: SqliteStore) -> None:
    gen._persist_redaction_job("a-fake")
    assert store.load_all_redaction_jobs() == {}


# ─── _persist_publish_record ────────────────────────────────────────


def test_persist_publish_record_writes(store: SqliteStore) -> None:
    a = _make_asset("a1")
    gen._assets["a1"] = a
    gen._chapters["a1"] = []
    gen._persist_asset("a1")
    gen._publish_records["pub-1"] = PublishRecord(
        id="pub-1", asset_id="a1", asset_version=1,
        destination="internal", destination_ref=None,
        publish_mode="full", status="success",
        url="/x", published_at=_now().isoformat(),
        published_by="anon",
    )
    gen._persist_publish_record("pub-1")
    rows = store.load_all_publish_records()
    assert len(rows) == 1
    assert rows[0]["id"] == "pub-1"


def test_persist_publish_record_missing_no_op(store: SqliteStore) -> None:
    gen._persist_publish_record("pub-fake")
    assert store.load_all_publish_records() == []


# ─── _bootstrap_from_db (重启 round-trip) ──────────────────────────


def test_bootstrap_loads_all_state(store: SqliteStore) -> None:
    # 灌一份完整 state, persist, 然后清 dict 再 bootstrap
    a = _make_asset("a1")
    ch = _make_chapter(0)
    gen._assets["a1"] = a
    gen._chapters["a1"] = [ch]
    gen._progress["a1"] = gen._initial_progress("a1")
    gen._evidence_by_chapter[ch.id] = [
        Evidence(
            id="e1", chapter_id=ch.id, event_id="ev1",
            event_version=1, span_start=0, span_end=10,
            citation_text="x", manually_added=False, stale=False,
            event_preview=EvidencePreview(
                event_id="ev1", source_type="github",
                source_ref="o/r", occurred_at=_now().isoformat(),
                content_excerpt="x",
            ),
        ),
    ]
    gen._redaction_jobs["a1"] = RedactionScanJob(
        job_id="j", asset_id="a1", status="done",
        progress=1.0, items=[],
    )
    gen._publish_records["pub-1"] = PublishRecord(
        id="pub-1", asset_id="a1", asset_version=1,
        destination="internal", destination_ref=None,
        publish_mode="full", status="success",
        url=None, published_at=_now().isoformat(),
        published_by="anon",
    )
    gen._persist_asset("a1")
    gen._persist_redaction_job("a1")
    gen._persist_publish_record("pub-1")

    # 清 dict 模拟重启
    gen._assets.clear()
    gen._chapters.clear()
    gen._evidence_by_chapter.clear()
    gen._progress.clear()
    gen._redaction_jobs.clear()
    gen._publish_records.clear()

    gen._bootstrap_from_db()
    assert "a1" in gen._assets
    assert "a1" in gen._progress
    assert len(gen._chapters["a1"]) == 1
    assert "ch-0" in gen._evidence_by_chapter
    assert "a1" in gen._redaction_jobs
    assert "pub-1" in gen._publish_records
