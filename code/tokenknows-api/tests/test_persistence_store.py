"""SqliteStore · asset/chapter/evidence/progress/redaction/publish CRUD.

datasource_health 已在 test_datasource_health.py 测过; 这里补其它方法.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.persistence.store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    return s


# ─── Assets ────────────────────────────────────────────────────────


def test_upsert_asset_insert(store: SqliteStore) -> None:
    store.upsert_asset(
        asset_id="a1", project_id="p1", status="draft",
        asset_type="weekly_report", updated_at="2026-05-22T10:00:00Z",
        json_str='{"id":"a1","title":"周报"}',
    )
    rows = store.load_all_assets()
    assert len(rows) == 1
    assert rows[0]["id"] == "a1"


def test_upsert_asset_update_on_conflict(store: SqliteStore) -> None:
    store.upsert_asset(
        asset_id="a1", project_id="p1", status="draft",
        asset_type="t", updated_at="2026-05-22T10:00:00Z",
        json_str='{"v":1}',
    )
    store.upsert_asset(
        asset_id="a1", project_id="p1", status="approved",
        asset_type="t", updated_at="2026-05-22T11:00:00Z",
        json_str='{"v":2}',
    )
    rows = store.load_all_assets()
    assert len(rows) == 1
    assert rows[0]["v"] == 2


def test_load_all_assets_ordered_by_updated_at_desc(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="2026-05-01T00:00:00Z", json_str='{"k":"old"}')
    store.upsert_asset(asset_id="a2", project_id="p", status="d", asset_type="t",
                       updated_at="2026-05-22T00:00:00Z", json_str='{"k":"new"}')
    rows = store.load_all_assets()
    assert rows[0]["k"] == "new"
    assert rows[1]["k"] == "old"


def test_delete_asset_cascade(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0, json_str="{}")
    # 删 asset, FK cascade 应级联删 chapter
    store.delete_asset("a1")
    assert store.load_all_assets() == []
    assert store.load_chapters_for_asset("a1") == []


# ─── Chapters ──────────────────────────────────────────────────────


def test_upsert_chapter_insert_and_update(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0,
                         json_str='{"title":"v1"}')
    # update
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0,
                         json_str='{"title":"v2"}')
    rows = store.load_chapters_for_asset("a1")
    assert len(rows) == 1
    assert rows[0]["title"] == "v2"


def test_replace_chapters_atomic(store: SqliteStore) -> None:
    """整批替换: 老的全删, 新的全入."""
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_chapter(chapter_id="old1", asset_id="a1", order_index=0,
                         json_str='{"v":"old"}')
    store.replace_chapters(
        "a1",
        [("new1", 0, '{"v":"new1"}'), ("new2", 1, '{"v":"new2"}')],
    )
    rows = store.load_chapters_for_asset("a1")
    assert len(rows) == 2
    assert rows[0]["v"] == "new1"
    assert rows[1]["v"] == "new2"


def test_load_chapters_ordered(store: SqliteStore) -> None:
    """按 order_index ASC 返回."""
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_chapter(chapter_id="c3", asset_id="a1", order_index=2, json_str='{"i":3}')
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0, json_str='{"i":1}')
    store.upsert_chapter(chapter_id="c2", asset_id="a1", order_index=1, json_str='{"i":2}')
    rows = store.load_chapters_for_asset("a1")
    assert [r["i"] for r in rows] == [1, 2, 3]


# ─── Progress ──────────────────────────────────────────────────────


def test_upsert_progress_and_load(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="g", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_progress("a1", "running", '{"stage":"content"}')
    loaded = store.load_progress("a1")
    assert loaded == {"stage": "content"}


def test_load_progress_missing_returns_none(store: SqliteStore) -> None:
    assert store.load_progress("a-no-such") is None


def test_upsert_progress_update_on_conflict(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="g", asset_type="t",
                       updated_at="t1", json_str="{}")
    store.upsert_progress("a1", "running", '{"stage":"outline"}')
    store.upsert_progress("a1", "done", '{"stage":"assess"}')
    loaded = store.load_progress("a1")
    assert loaded["stage"] == "assess"


# ─── Evidence ──────────────────────────────────────────────────────


def test_replace_evidence_atomic(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0, json_str="{}")

    store.replace_evidence("c1", [("e1", '{"k":1}'), ("e2", '{"k":2}')])
    rows = store.load_evidence_for_chapter("c1")
    assert len(rows) == 2

    # 替换为 1 条
    store.replace_evidence("c1", [("e3", '{"k":3}')])
    rows = store.load_evidence_for_chapter("c1")
    assert len(rows) == 1
    assert rows[0]["k"] == 3


def test_load_all_evidence_grouped_by_chapter(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_chapter(chapter_id="c1", asset_id="a1", order_index=0, json_str="{}")
    store.upsert_chapter(chapter_id="c2", asset_id="a1", order_index=1, json_str="{}")
    store.replace_evidence("c1", [("e1", '{"k":1}')])
    store.replace_evidence("c2", [("e2", '{"k":2}'), ("e3", '{"k":3}')])
    grouped = store.load_all_evidence()
    assert len(grouped["c1"]) == 1
    assert len(grouped["c2"]) == 2


# ─── Redaction jobs ────────────────────────────────────────────────


def test_upsert_redaction_job_and_load(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_redaction_job("a1", '{"status":"pending"}')
    jobs = store.load_all_redaction_jobs()
    assert jobs == {"a1": {"status": "pending"}}


def test_upsert_redaction_job_update(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_redaction_job("a1", '{"status":"pending"}')
    store.upsert_redaction_job("a1", '{"status":"done"}')
    jobs = store.load_all_redaction_jobs()
    assert jobs["a1"]["status"] == "done"


# ─── Publish records ──────────────────────────────────────────────


def test_upsert_publish_record_and_load(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_publish_record(
        record_id="r1", asset_id="a1",
        published_at="2026-05-22T10:00:00Z",
        json_str='{"destination":"internal"}',
    )
    rows = store.load_all_publish_records()
    assert len(rows) == 1
    assert rows[0]["destination"] == "internal"


def test_load_publish_records_ordered_desc(store: SqliteStore) -> None:
    store.upsert_asset(asset_id="a1", project_id="p", status="d", asset_type="t",
                       updated_at="t", json_str="{}")
    store.upsert_publish_record("r1", "a1", "2026-05-01T00:00:00Z",
                                '{"k":"old"}')
    store.upsert_publish_record("r2", "a1", "2026-05-22T00:00:00Z",
                                '{"k":"new"}')
    rows = store.load_all_publish_records()
    assert rows[0]["k"] == "new"
    assert rows[1]["k"] == "old"


# ─── Events get_event 单条查询 ────────────────────────────────────


def test_get_event_returns_none_for_missing(store: SqliteStore) -> None:
    assert store.get_event("evt-fake") is None


def test_get_event_returns_dict_after_upsert(store: SqliteStore) -> None:
    payload = json.dumps({"id": "evt-1", "title": "x"})
    store.upsert_event(
        event_id="evt-1", project_id="p", source_type="github",
        event_type="commit", occurred_at="2026-05-22T10:00:00Z",
        ingested_at="2026-05-22T10:00:01Z", content_hash="h1",
        json_str=payload,
    )
    found = store.get_event("evt-1")
    assert found == {"id": "evt-1", "title": "x"}
