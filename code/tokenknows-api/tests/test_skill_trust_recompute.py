"""T61 · Daily trust_score recompute.

覆盖:
- recompute_all_trust_scores:
  * active/draft 被刷
  * deprecated/locked 跳过
  * trust_score 真有变才写 (avoid disk write)
  * recency_decay 随 last_used_at 衰减
- skill_trust_recompute_job 与 scheduler 注册
"""

from __future__ import annotations

import math
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
    locked=False,
    trust=0.5,
    usage=10,
    acc=5,
    rej=5,
    last_used_at: datetime | None = None,
) -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id=skill_id,
        project_id="p",
        name=f"name-{skill_id}",
        version=1,
        skill_md="---\n---\n",
        embedding=None,
        metrics=SkillMetrics(
            usage_count=usage,
            acceptance_count=acc,
            rejection_count=rej,
            avg_acceptance_rate=acc / max(1, acc + rej),
            trust_score=trust,
        ),
        distilled_from=[],
        distilled_at=now,
        last_used_at=last_used_at,
        locked=locked,
        status=status,
        parent_skill_id=None,
        contributors=[],
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state="approved",
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


# ─── recompute_all_trust_scores ──────────────────────────


def test_recompute_skips_deprecated(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="s-dep", status="deprecated", trust=0.1)
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["scanned"] == 1
    assert result["updated"] == 0
    assert result["skipped"] == 1
    persisted = skill_service.get_skill("s-dep")
    assert persisted.metrics.trust_score == 0.1  # 不动


def test_recompute_skips_locked(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="s-lock", locked=True, trust=0.9)
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["skipped"] == 1
    assert result["updated"] == 0


def test_recompute_updates_active_when_decayed(fresh_db):
    """active + last_used_at 久 → recency_decay 使 trust 应下降."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=60)
    # 故意把现有 trust 设高 (0.95), 但 recency 应让它降下来
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-decayed",
            trust=0.95,
            usage=20,
            acc=18, rej=2,
            last_used_at=long_ago,
        )
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["updated"] == 1
    persisted = skill_service.get_skill("s-decayed")
    # base ≈ 19/22 = 0.86, recency = exp(-60/30) ≈ 0.135, conf = 1
    # → ≈ 0.116
    assert persisted.metrics.trust_score < 0.2
    assert persisted.metrics.trust_score < 0.95


def test_recompute_noop_when_no_change(fresh_db):
    """trust 已经是正确值 → 不更新 (省 disk write)."""
    now = datetime.now(timezone.utc)
    # 先用真正算法算一遍, 再放回去
    from app.services.skill_service import _compute_trust_score
    correct_trust = _compute_trust_score(
        acceptance=5, rejection=5, usage=10, last_used_at=now,
    )
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-correct",
            trust=correct_trust,
            usage=10, acc=5, rej=5,
            last_used_at=now,
        )
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["scanned"] == 1
    assert result["updated"] == 0  # noop


def test_recompute_handles_draft_status(fresh_db):
    """draft 也应被刷 (虽未上线, trust 仍影响 select 排序)."""
    now = datetime.now(timezone.utc)
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-draft", status="draft", trust=0.5,
            usage=20, acc=15, rej=5,
            last_used_at=now,
        )
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["scanned"] == 1
    # 0.5 与真值 (0.7+ 因近期+高 acc) 差异 > 1e-4 → 应更新
    assert result["updated"] == 1


def test_recompute_mixed_states_counts(fresh_db):
    """混合: 1 active(已衰减) + 1 deprecated + 1 locked → updated=1, skipped=2."""
    now = datetime.now(timezone.utc)
    long_ago = now - timedelta(days=30)
    # active skill 故意把 trust 设错 (设成 0.99), 真值会因 decay 远低
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-active",
            trust=0.99,
            usage=10, acc=5, rej=5,
            last_used_at=long_ago,
        )
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-dep", status="deprecated", trust=0.1)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-lock", locked=True, trust=0.9)
    )
    result = skill_pool.recompute_all_trust_scores()
    assert result["scanned"] == 3
    assert result["skipped"] == 2
    assert result["updated"] == 1


# ─── job + scheduler ─────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_trust_recompute_job_runs(fresh_db):
    from app.services.auto_trigger.jobs import skill_trust_recompute_job
    now = datetime.now(timezone.utc)
    skill_service.get_registry().add(
        _make_skill(skill_id="s-active", trust=0.5, last_used_at=now)
    )
    await skill_trust_recompute_job()  # 不抛


@pytest.mark.asyncio
async def test_skill_trust_recompute_job_swallow_errors(monkeypatch):
    from app.services.auto_trigger.jobs import skill_trust_recompute_job

    def _raise():
        raise RuntimeError("explode")

    monkeypatch.setattr(
        "app.services.skill.pool.recompute_all_trust_scores", _raise
    )
    await skill_trust_recompute_job()  # 不抛


def test_scheduler_registers_trust_recompute_job():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.services.auto_trigger.scheduler import _register_fixed_jobs

    sched = AsyncIOScheduler()
    _register_fixed_jobs(sched)
    job = sched.get_job("skill_trust_recompute")
    assert job is not None
    assert "trust_score 重算" in job.name
