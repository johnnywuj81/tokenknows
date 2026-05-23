"""T59 · skill_evolve_checker_job 真跑.

覆盖:
- collect_failing_chapters_for_skill: 跨 asset / 过滤 approval_state
- collect_evolve_candidates: usage / acc_rate 阈值
- skill_evolve_checker_job:
  * 无候选 → 不触发 evolve
  * 候选无 failing chapters → 跳过, 计 no_failing
  * 候选 + failing → 真调 evolve_skill_v2 (mock LLM); 通知 contributors
  * 单 skill 异常不阻断
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
    skill_id: str = "skill-evo",
    project_id: str = "proj-X",
    usage: int = 20,
    acc: int = 4,
    rej: int = 16,
    contributors=("ou-a", "ou-b"),
    status="active",
    locked: bool = False,
) -> Skill:
    now = datetime.now(timezone.utc)
    metrics = SkillMetrics(
        usage_count=usage,
        acceptance_count=acc,
        rejection_count=rej,
        avg_acceptance_rate=acc / max(1, acc + rej),
        trust_score=0.4,
    )
    return Skill(
        id=skill_id,
        project_id=project_id,
        name=f"name-{skill_id}",
        version=1,
        skill_md="---\nname: x\n---\n# body",
        embedding=None,
        metrics=metrics,
        distilled_from=[],
        distilled_at=now,
        last_used_at=now,
        locked=locked,
        status=status,
        parent_skill_id=None,
        contributors=list(contributors),
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state="approved",  # 已上线的 skill
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


# ─── collect_evolve_candidates ────────────────────────────


def test_collect_candidates_filters_low_usage(fresh_db):
    """usage < 20 不入选."""
    s = _make_skill(usage=5, acc=1, rej=4)
    skill_service.get_registry().add(s)
    candidates = skill_pool.collect_evolve_candidates()
    assert candidates == []


def test_collect_candidates_filters_high_acc_rate(fresh_db):
    """acc_rate >= 0.5 不入选."""
    s = _make_skill(usage=30, acc=20, rej=10)  # 0.67
    skill_service.get_registry().add(s)
    candidates = skill_pool.collect_evolve_candidates()
    assert candidates == []


def test_collect_candidates_filters_locked(fresh_db):
    s = _make_skill(usage=30, acc=5, rej=25, locked=True)
    skill_service.get_registry().add(s)
    candidates = skill_pool.collect_evolve_candidates()
    assert candidates == []


def test_collect_candidates_picks_underperforming(fresh_db):
    s = _make_skill(skill_id="skill-bad", usage=25, acc=4, rej=21)
    skill_service.get_registry().add(s)
    candidates = skill_pool.collect_evolve_candidates()
    assert len(candidates) == 1
    assert candidates[0]["skill_id"] == "skill-bad"
    assert candidates[0]["usage_count"] == 25


def test_collect_candidates_multiple(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="s-1", usage=30, acc=5, rej=25)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-2", usage=22, acc=3, rej=19)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-good", usage=30, acc=20, rej=10)  # 不该入选
    )
    candidates = skill_pool.collect_evolve_candidates()
    ids = {c["skill_id"] for c in candidates}
    assert ids == {"s-1", "s-2"}


# ─── collect_failing_chapters_for_skill ──────────────────


def test_collect_failing_chapters_filters_by_state_and_skill(fresh_db):
    """需要 chapter.approval_state == 'rejected' 且 applied_skills 含 skill_id."""
    from app.services import generation_service
    from types import SimpleNamespace

    # 清空内存 cache
    generation_service._chapters.clear()
    generation_service._assets.clear()

    project_id = "proj-X"
    skill_id = "skill-target"

    generation_service._assets["a-1"] = SimpleNamespace(
        id="a-1", project_id=project_id
    )

    class _Ch:
        def __init__(self, cid, state, applied):
            self.id = cid
            self.approval_state = state
            self.applied_skills = applied
        def model_dump(self, mode="json"):
            return {
                "id": self.id,
                "approval_state": self.approval_state,
                "applied_skills": self.applied_skills,
            }

    generation_service._chapters["a-1"] = [
        # 命中: rejected + applied 含 target
        _Ch("c-1", "rejected", [{"skill_id": skill_id}]),
        # 不中: approved
        _Ch("c-2", "approved", [{"skill_id": skill_id}]),
        # 不中: rejected 但 applied 不含 target
        _Ch("c-3", "rejected", [{"skill_id": "other-skill"}]),
        # 不中: rejected 但 applied 为空
        _Ch("c-4", "rejected", []),
    ]
    failing = skill_pool.collect_failing_chapters_for_skill(project_id, skill_id)
    assert len(failing) == 1
    assert failing[0]["id"] == "c-1"


def test_collect_failing_chapters_skips_other_projects(fresh_db):
    from app.services import generation_service
    from types import SimpleNamespace

    generation_service._chapters.clear()
    generation_service._assets.clear()
    generation_service._assets["a-other"] = SimpleNamespace(
        id="a-other", project_id="proj-DIFFERENT"
    )

    class _Ch:
        def __init__(self):
            self.id = "c-x"
            self.approval_state = "rejected"
            self.applied_skills = [{"skill_id": "s-target"}]
        def model_dump(self, mode="json"):
            return {"id": self.id, "approval_state": self.approval_state}

    generation_service._chapters["a-other"] = [_Ch()]
    failing = skill_pool.collect_failing_chapters_for_skill(
        "proj-X", "s-target"
    )
    assert failing == []  # 不跨 project


# ─── skill_evolve_checker_job ────────────────────────────


@pytest.mark.asyncio
async def test_evolve_job_no_candidates_logs_only(fresh_db):
    from app.services.auto_trigger.jobs import skill_evolve_checker_job
    # 不 seed 任何候选
    skill_service.get_registry().add(
        _make_skill(skill_id="s-fine", usage=10, acc=8, rej=2)
    )
    await skill_evolve_checker_job()  # 不应抛


@pytest.mark.asyncio
async def test_evolve_job_candidate_no_failing_chapters(fresh_db, monkeypatch):
    """有候选但无 failing chapters → 跳过."""
    from app.services.auto_trigger.jobs import skill_evolve_checker_job

    # 候选
    skill_service.get_registry().add(
        _make_skill(skill_id="s-bad", usage=25, acc=4, rej=21)
    )
    # 但 _collect_failing_chapters_for_skill 返空
    monkeypatch.setattr(
        skill_pool, "collect_failing_chapters_for_skill",
        lambda _p, _s: [],
    )
    await skill_evolve_checker_job()  # 不抛


@pytest.mark.asyncio
async def test_evolve_job_calls_evolve_and_notifies(fresh_db, monkeypatch):
    from app.services.auto_trigger import jobs as auto_jobs

    # 候选
    skill_service.get_registry().add(
        _make_skill(
            skill_id="s-evolve", usage=25, acc=4, rej=21,
            contributors=("ou-a", "ou-b"),
        )
    )

    # mock collect_failing_chapters_for_skill 返非空
    failing_ch = [
        {
            "id": "c-fail",
            "asset_id": "a-1",
            "title": "rejected chapter",
            "content": "...content...",
        }
    ]
    monkeypatch.setattr(
        skill_pool, "collect_failing_chapters_for_skill",
        lambda _p, _s: failing_ch,
    )

    # mock evolve_skill_v2 返回 fake new skill
    new_skill = _make_skill(
        skill_id="s-evolve-v2", usage=0, acc=0, rej=0, status="draft",
    )

    async def _fake_evolve(skill_id, failing_chapters, project_label=None):
        return new_skill

    monkeypatch.setattr(skill_service, "evolve_skill_v2", _fake_evolve)

    # spy notify_review_request (positional skill + kw only after)
    notifies = []
    def _fake_notify(skill, *, reviewer_user_ids, author_user_id):
        notifies.append({
            "skill_id": skill.id,
            "reviewers": list(reviewer_user_ids),
            "author": author_user_id,
        })
        return len(reviewer_user_ids)

    from app.services.skill import review_notifier
    monkeypatch.setattr(
        review_notifier, "notify_review_request", _fake_notify
    )

    await auto_jobs.skill_evolve_checker_job()

    # 通知应触发, author='system-evolve'
    assert len(notifies) == 1
    assert notifies[0]["skill_id"] == "s-evolve-v2"
    assert set(notifies[0]["reviewers"]) == {"ou-a", "ou-b"}
    assert notifies[0]["author"] == "system-evolve"


@pytest.mark.asyncio
async def test_evolve_job_single_skill_failure_doesnt_break_others(
    fresh_db, monkeypatch
):
    """一个 skill evolve 失败应继续下一个."""
    from app.services.auto_trigger import jobs as auto_jobs

    skill_service.get_registry().add(
        _make_skill(skill_id="s-explode", usage=25, acc=4, rej=21)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="s-ok", usage=25, acc=4, rej=21)
    )

    monkeypatch.setattr(
        skill_pool, "collect_failing_chapters_for_skill",
        lambda _p, _s: [{"id": "c-x"}],
    )

    call_count = [0]

    async def _evolve_with_failure(skill_id, failing_chapters, project_label=None):
        call_count[0] += 1
        if skill_id == "s-explode":
            raise RuntimeError("boom")
        return _make_skill(skill_id=f"{skill_id}-v2", status="draft")

    monkeypatch.setattr(
        skill_service, "evolve_skill_v2", _evolve_with_failure
    )
    monkeypatch.setattr(
        "app.services.skill.review_notifier.notify_review_request",
        lambda skill, **k: 0,
    )

    # 不抛
    await auto_jobs.skill_evolve_checker_job()
    # 2 个候选都被调过 evolve_skill_v2
    assert call_count[0] == 2
