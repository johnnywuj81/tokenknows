"""Skill schema + skills 表 CRUD (v0.2).

覆盖:
- Skill / SkillMetrics / SkillDistillSource pydantic round-trip
- SkillDistillRequest / SkillUpdateRequest 边界
- SqliteStore.upsert_skill / list_skills / get_skill / delete_skill / load_all_skills
- 排序 (trust_score DESC, updated_at DESC)
- status 过滤
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.persistence.store import SqliteStore
from app.schemas.skill import (
    Skill,
    SkillApplicationRecord,
    SkillDistillRequest,
    SkillDistillSource,
    SkillMetrics,
    SkillUpdateRequest,
)


# ─── Skill 模型 ─────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_skill(**overrides) -> Skill:
    defaults = dict(
        id="skill-001",
        project_id="proj-demo",
        name="pr-summary-formatting",
        version=1,
        skill_md="---\nname: pr-summary-formatting\n---\n# 适用场景\n...",
        distilled_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Skill(**defaults)


def test_skill_minimal_construct_defaults() -> None:
    s = _make_skill()
    assert s.metrics.usage_count == 0
    assert s.metrics.trust_score == 0.5
    assert s.status == "draft"
    assert s.locked is False
    assert s.distilled_from == []
    assert s.embedding is None
    assert s.parent_skill_id is None


def test_skill_round_trip_json() -> None:
    src = SkillDistillSource(
        chapter_id="ch-1",
        asset_id="a-1",
        asset_version=2,
        quoted_at=_now(),
    )
    s = _make_skill(
        embedding=[0.1, 0.2, 0.3],
        metrics=SkillMetrics(
            usage_count=10,
            acceptance_count=8,
            rejection_count=2,
            avg_acceptance_rate=0.8,
            trust_score=0.75,
        ),
        distilled_from=[src],
        status="active",
        locked=True,
    )
    dump = s.model_dump_json()
    back = Skill.model_validate_json(dump)
    assert back.embedding == [0.1, 0.2, 0.3]
    assert back.metrics.trust_score == 0.75
    assert back.distilled_from[0].chapter_id == "ch-1"
    assert back.locked is True


def test_skill_metrics_bounds_clamped() -> None:
    """trust_score / avg_acceptance_rate 必须 0-1."""
    with pytest.raises(ValidationError):
        SkillMetrics(trust_score=1.5)
    with pytest.raises(ValidationError):
        SkillMetrics(avg_acceptance_rate=-0.1)


def test_skill_distill_request_min_sources() -> None:
    """至少 1 个 source chapter."""
    req = SkillDistillRequest(source_chapter_ids=["ch-1"])
    assert len(req.source_chapter_ids) == 1
    with pytest.raises(ValidationError):
        SkillDistillRequest(source_chapter_ids=[])


def test_skill_distill_request_max_sources() -> None:
    """最多 10 个 source chapter (避免上下文爆炸)."""
    req = SkillDistillRequest(source_chapter_ids=[f"ch-{i}" for i in range(10)])
    assert len(req.source_chapter_ids) == 10
    with pytest.raises(ValidationError):
        SkillDistillRequest(source_chapter_ids=[f"ch-{i}" for i in range(11)])


def test_skill_update_request_partial() -> None:
    """PATCH 半字段允许."""
    upd = SkillUpdateRequest(locked=True)
    assert upd.locked is True
    assert upd.skill_md is None
    assert upd.status is None


def test_skill_application_record_chapter_format() -> None:
    """SkillApplicationRecord 可直接 dump 到 chapter.applied_skills."""
    rec = SkillApplicationRecord(
        skill_id="skill-001",
        version=2,
        applied_at=_now(),
        cosine_similarity=0.87,
    )
    payload = rec.model_dump(mode="json")
    assert payload["skill_id"] == "skill-001"
    assert payload["cosine_similarity"] == 0.87


# ─── 持久化层 ───────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    return s


def test_skills_table_created_on_bootstrap(store: SqliteStore) -> None:
    stats = store.stats()
    assert "skills" in stats
    assert stats["skills"] == 0


def test_upsert_skill_insert(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="skill-001",
        project_id="proj-demo",
        name="pr-summary",
        version=1,
        status="draft",
        trust_score=0.5,
        updated_at="2026-05-22T10:00:00Z",
        json_str=json.dumps({"id": "skill-001", "name": "pr-summary"}),
    )
    items = store.list_skills("proj-demo")
    assert len(items) == 1
    assert items[0]["id"] == "skill-001"


def test_upsert_skill_update_on_conflict(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="skill-001",
        project_id="proj-demo",
        name="pr-summary",
        version=1,
        status="draft",
        trust_score=0.5,
        updated_at="2026-05-22T10:00:00Z",
        json_str=json.dumps({"v": 1}),
    )
    store.upsert_skill(
        skill_id="skill-001",
        project_id="proj-demo",
        name="pr-summary",
        version=2,
        status="active",
        trust_score=0.85,
        updated_at="2026-05-22T11:00:00Z",
        json_str=json.dumps({"v": 2}),
    )
    items = store.list_skills("proj-demo")
    assert len(items) == 1
    assert items[0]["v"] == 2


def test_list_skills_filtered_by_status(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="s1", project_id="p", name="n1", version=1,
        status="draft", trust_score=0.4, updated_at="t1", json_str='{"k":1}',
    )
    store.upsert_skill(
        skill_id="s2", project_id="p", name="n2", version=1,
        status="active", trust_score=0.9, updated_at="t2", json_str='{"k":2}',
    )
    store.upsert_skill(
        skill_id="s3", project_id="p", name="n3", version=1,
        status="deprecated", trust_score=0.2, updated_at="t3", json_str='{"k":3}',
    )
    active = store.list_skills("p", status="active")
    assert len(active) == 1
    assert active[0]["k"] == 2


def test_list_skills_ordered_by_trust_score_desc(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="s1", project_id="p", name="n", version=1,
        status="active", trust_score=0.3, updated_at="t",
        json_str='{"label":"low"}',
    )
    store.upsert_skill(
        skill_id="s2", project_id="p", name="n", version=2,
        status="active", trust_score=0.9, updated_at="t",
        json_str='{"label":"high"}',
    )
    store.upsert_skill(
        skill_id="s3", project_id="p", name="n", version=3,
        status="active", trust_score=0.6, updated_at="t",
        json_str='{"label":"mid"}',
    )
    items = store.list_skills("p")
    assert [s["label"] for s in items] == ["high", "mid", "low"]


def test_list_skills_isolated_by_project(store: SqliteStore) -> None:
    """项目级私有: project_id 隔离."""
    store.upsert_skill(
        skill_id="s1", project_id="proj-A", name="n", version=1,
        status="active", trust_score=0.8, updated_at="t",
        json_str='{"p":"A"}',
    )
    store.upsert_skill(
        skill_id="s2", project_id="proj-B", name="n", version=1,
        status="active", trust_score=0.8, updated_at="t",
        json_str='{"p":"B"}',
    )
    a = store.list_skills("proj-A")
    b = store.list_skills("proj-B")
    assert len(a) == 1 and a[0]["p"] == "A"
    assert len(b) == 1 and b[0]["p"] == "B"


def test_get_skill_returns_none_for_missing(store: SqliteStore) -> None:
    assert store.get_skill("not-exist") is None


def test_get_skill_returns_full_json(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="s1", project_id="p", name="n", version=1,
        status="active", trust_score=0.5, updated_at="t",
        json_str='{"id":"s1","skill_md":"# Body"}',
    )
    got = store.get_skill("s1")
    assert got == {"id": "s1", "skill_md": "# Body"}


def test_delete_skill(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="s1", project_id="p", name="n", version=1,
        status="active", trust_score=0.5, updated_at="t",
        json_str='{"id":"s1"}',
    )
    store.delete_skill("s1")
    assert store.get_skill("s1") is None
    assert store.list_skills("p") == []


def test_load_all_skills_returns_every_project(store: SqliteStore) -> None:
    store.upsert_skill(
        skill_id="s1", project_id="proj-A", name="n", version=1,
        status="active", trust_score=0.5, updated_at="2026-05-22T11:00:00Z",
        json_str='{"id":"s1"}',
    )
    store.upsert_skill(
        skill_id="s2", project_id="proj-B", name="n", version=1,
        status="draft", trust_score=0.5, updated_at="2026-05-22T12:00:00Z",
        json_str='{"id":"s2"}',
    )
    all_skills = store.load_all_skills()
    assert {s["id"] for s in all_skills} == {"s1", "s2"}
    # updated_at DESC: s2 在前
    assert all_skills[0]["id"] == "s2"


def test_skill_idempotent_bootstrap_on_existing_db(tmp_path: Path) -> None:
    """老 DB 二次 bootstrap 不应报错 (CREATE TABLE IF NOT EXISTS)."""
    db_path = tmp_path / "state.sqlite"
    s1 = SqliteStore(db_path)
    s1._apply_schema()
    # 关掉再开
    s2 = SqliteStore(db_path)
    s2._apply_schema()
    # 仍可写
    s2.upsert_skill(
        skill_id="s", project_id="p", name="n", version=1,
        status="draft", trust_score=0.5, updated_at="t", json_str="{}",
    )
    assert s2.stats()["skills"] == 1
