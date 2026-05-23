"""T60 · Skill dormancy + low-trust 自动 deprecate.

覆盖:
- collect_deprecation_candidates:
  * dormant (last_used_at > 60d)
  * never used + created_at > 60d → also dormant
  * low_trust (trust < 0.2)
  * 跳过 deprecated/locked/非 active
- skill_deprecation_sweep_job:
  * 无候选 → noop
  * 真转 deprecated + 通知
  * race: 候选 active 但 job 跑时已变 → 跳
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import Skill, SkillMetrics
from app.services import skill_service
from app.services.skill import pool as skill_pool


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    skill_service.reset_registry_for_tests()
    return s


def _make_skill(
    *,
    skill_id="s-1",
    status="active",
    trust=0.5,
    last_used_at: datetime | None = None,
    created_offset_days: float = 1.0,
    locked: bool = False,
    contributors=("ou-a",),
    last_reviewer_id: str | None = None,
) -> Skill:
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=created_offset_days)
    return Skill(
        id=skill_id,
        project_id="proj-X",
        name=f"name-{skill_id}",
        version=1,
        skill_md="---\n---\n",
        embedding=None,
        metrics=SkillMetrics(
            usage_count=1, acceptance_count=1, rejection_count=0,
            avg_acceptance_rate=1.0, trust_score=trust,
        ),
        distilled_from=[],
        distilled_at=created,
        last_used_at=last_used_at,
        locked=locked,
        status=status,
        parent_skill_id=None,
        contributors=list(contributors),
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state="approved",
        review_history=[],
        last_reviewer_id=last_reviewer_id,
        last_reviewed_at=None,
        created_at=created,
        updated_at=created,
    )


# ─── collect_deprecation_candidates ──────────────────────


def test_dormant_by_last_used_at(fresh_db):
    now = datetime.now(timezone.utc)
    long_ago = now - timedelta(days=90)
    skill_service.get_registry().add(
        _make_skill(skill_id="s-dormant", last_used_at=long_ago)
    )
    candidates = skill_pool.collect_deprecation_candidates()
    assert len(candidates) == 1
    assert candidates[0]["skill_id"] == "s-dormant"
    assert candidates[0]["reason"] == "dormant"


def test_dormant_by_never_used_old_created(fresh_db):
    """从未用过 + created > 60d → dormant."""
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-never-used",
            last_used_at=None,
            created_offset_days=90.0,
        )
    )
    candidates = skill_pool.collect_deprecation_candidates()
    assert len(candidates) == 1
    assert candidates[0]["reason"] == "dormant"


def test_never_used_recent_not_dormant(fresh_db):
    """从未用过 + created < 60d → 不算 dormant (新 skill 给宽限期)."""
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-new",
            last_used_at=None,
            created_offset_days=10.0,
            trust=0.5,  # 中等 trust 也不动
        )
    )
    candidates = skill_pool.collect_deprecation_candidates()
    assert candidates == []


def test_low_trust(fresh_db):
    """trust < 0.2 → low_trust 候选."""
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-low-trust",
            trust=0.15,
            last_used_at=datetime.now(timezone.utc),  # 最近用过
        )
    )
    candidates = skill_pool.collect_deprecation_candidates()
    assert len(candidates) == 1
    assert candidates[0]["reason"] == "low_trust"


def test_skips_deprecated_status(fresh_db):
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-already-dep", status="deprecated",
            trust=0.1, last_used_at=None, created_offset_days=200,
        )
    )
    assert skill_pool.collect_deprecation_candidates() == []


def test_skips_locked(fresh_db):
    """locked skill 不动 (人工固化版本)."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=200)
    skill_service.get_registry().add(
        _make_skill(skill_id="s-locked", locked=True, last_used_at=long_ago)
    )
    assert skill_pool.collect_deprecation_candidates() == []


def test_skips_draft(fresh_db):
    """draft skill 不动 (还没正式发布)."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=200)
    skill_service.get_registry().add(
        _make_skill(skill_id="s-draft", status="draft", last_used_at=long_ago)
    )
    assert skill_pool.collect_deprecation_candidates() == []


def test_dormant_takes_precedence_over_low_trust(fresh_db):
    """同时 dormant + low_trust → reason='dormant' (dormant 优先)."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-both",
            last_used_at=long_ago,
            trust=0.1,
        )
    )
    candidates = skill_pool.collect_deprecation_candidates()
    assert candidates[0]["reason"] == "dormant"


# ─── skill_deprecation_sweep_job ─────────────────────────


@pytest.mark.asyncio
async def test_sweep_no_candidates_noop(fresh_db):
    from app.services.auto_trigger.jobs import skill_deprecation_sweep_job
    skill_service.get_registry().add(
        _make_skill(skill_id="s-fine", trust=0.5)
    )
    await skill_deprecation_sweep_job()


@pytest.mark.asyncio
async def test_sweep_transitions_active_to_deprecated(fresh_db, monkeypatch):
    from app.services.auto_trigger.jobs import skill_deprecation_sweep_job
    from app.services.skill import review_notifier

    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-old", last_used_at=long_ago,
            contributors=("ou-author",),
            last_reviewer_id="ou-bob",
        )
    )

    notifies = []
    def _spy(skill, *, type_, author_user_id, reviewer_id, reason=None):
        notifies.append({
            "skill_id": skill.id,
            "type": type_,
            "author": author_user_id,
            "reviewer": reviewer_id,
            "reason": reason,
        })
        return 1
    monkeypatch.setattr(review_notifier, "notify_review_decision", _spy)

    await skill_deprecation_sweep_job()

    persisted = skill_service.get_skill("s-old")
    assert persisted is not None
    assert persisted.status == "deprecated"
    # 通知发出
    assert len(notifies) == 1
    assert notifies[0]["type"] == "skill_review_rejected"
    assert notifies[0]["reviewer"] == "system-deprecate"
    assert "dormant" in (notifies[0]["reason"] or "")


@pytest.mark.asyncio
async def test_sweep_race_skill_no_longer_active(fresh_db, monkeypatch):
    """候选还在 active, 但 job 跑时已转 deprecated → 跳过."""
    from app.services.auto_trigger.jobs import skill_deprecation_sweep_job

    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    skill = _make_skill(skill_id="s-race", last_used_at=long_ago)
    skill_service.get_registry().add(skill)

    # 候选已采集; 模拟人手动转 deprecated
    race_skill = skill.model_copy(update={"status": "deprecated"})
    skill_service.get_registry().update(race_skill)

    # 通知 spy: 不应被调
    notify_count = [0]
    monkeypatch.setattr(
        "app.services.skill.review_notifier.notify_review_decision",
        lambda skill, **k: notify_count.__setitem__(0, notify_count[0] + 1),
    )

    await skill_deprecation_sweep_job()
    assert notify_count[0] == 0


@pytest.mark.asyncio
async def test_sweep_single_failure_continues(fresh_db, monkeypatch):
    from app.services.auto_trigger.jobs import skill_deprecation_sweep_job

    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    skill_service.get_registry().add(
        _make_skill(skill_id="s-explode", last_used_at=long_ago)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-ok", last_used_at=long_ago)
    )

    # mock notify to track
    call_count = [0]

    def _notify(skill, **k):
        call_count[0] += 1
        if skill.id == "s-explode":
            raise RuntimeError("notify failed")
        return 1

    monkeypatch.setattr(
        "app.services.skill.review_notifier.notify_review_decision",
        _notify,
    )

    await skill_deprecation_sweep_job()
    # 两个都被转 deprecated
    assert skill_service.get_skill("s-ok").status == "deprecated"
    assert skill_service.get_skill("s-explode").status == "deprecated"


# ─── scheduler 注册 ──────────────────────────────────────


def test_scheduler_registers_deprecation_sweep_job():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.services.auto_trigger.scheduler import _register_fixed_jobs

    sched = AsyncIOScheduler()
    _register_fixed_jobs(sched)
    job = sched.get_job("skill_deprecation_sweep")
    assert job is not None
    assert "Skill 自动归档" in job.name
