"""T56 · Skill review_state schema + 状态机.

覆盖:
- ReviewState 4 状态 Literal 校验
- ReviewRecord 必填字段
- Skill 新 4 字段 default + 旧 JSON backfill
- can_review_transition legal/illegal 矩阵
- submit_for_review: status / review_state 前置 + happy + rejected→repeating
- approve: 同时改 status draft→active + 写 last_reviewer_id
- reject: 保留 draft + reason 必填
- latest_review_record
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.skill import (
    ReviewRecord,
    ReviewState,
    Skill,
    SkillMetrics,
)
from app.services.skill.review import (
    InvalidReviewTransition,
    approve,
    can_review_transition,
    latest_review_record,
    reject,
    submit_for_review,
)


def _make(
    *,
    status="draft",
    review_state: ReviewState = "not_submitted",
    review_history: list[ReviewRecord] | None = None,
    last_reviewer_id: str | None = None,
) -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id="skill-rv-1",
        project_id="proj-X",
        name="test",
        version=1,
        skill_md="---\n---\n",
        embedding=None,
        metrics=SkillMetrics(),
        distilled_from=[],
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status=status,
        parent_skill_id=None,
        contributors=[],
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state=review_state,
        review_history=review_history or [],
        last_reviewer_id=last_reviewer_id,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


# ─── ReviewState Literal ─────────────────────────────────


@pytest.mark.parametrize(
    "state", ["not_submitted", "pending_review", "approved", "rejected"]
)
def test_review_state_all_4_valid(state):
    s = _make(review_state=state)
    assert s.review_state == state


def test_review_state_invalid_string_rejected():
    with pytest.raises(ValidationError):
        _make(review_state="totally_made_up")  # type: ignore[arg-type]


# ─── ReviewRecord 校验 ───────────────────────────────────


def test_review_record_action_literal():
    r = ReviewRecord(
        reviewer_id="r-1",
        action="approve",
        timestamp=datetime.now(timezone.utc),
    )
    assert r.action == "approve"


def test_review_record_invalid_action_rejected():
    with pytest.raises(ValidationError):
        ReviewRecord(
            reviewer_id="r-1",
            action="maybe",  # type: ignore[arg-type]
            timestamp=datetime.now(timezone.utc),
        )


# ─── 新字段 default + backfill ───────────────────────────


def test_new_review_fields_default():
    s = _make()
    assert s.review_state == "not_submitted"
    assert s.review_history == []
    assert s.last_reviewer_id is None
    assert s.last_reviewed_at is None


def test_old_skill_json_backfills_review_fields():
    """v0.5 之前的 JSON 无 review_* 字段; load 时应自动填 default."""
    now = datetime.now(timezone.utc).isoformat()
    legacy = {
        "id": "skill-legacy",
        "project_id": "p",
        "name": "legacy",
        "version": 1,
        "skill_md": "---\n---\n",
        "embedding": None,
        "metrics": {
            "usage_count": 0, "acceptance_count": 0, "rejection_count": 0,
            "avg_acceptance_rate": 0, "trust_score": 0.5,
        },
        "distilled_from": [],
        "distilled_at": now,
        "last_used_at": None,
        "locked": False,
        "status": "active",
        "parent_skill_id": None,
        "created_at": now,
        "updated_at": now,
    }
    s = Skill.model_validate(legacy)
    assert s.review_state == "not_submitted"
    assert s.review_history == []
    assert s.last_reviewer_id is None
    # round-trip
    s2 = Skill.model_validate(json.loads(s.model_dump_json()))
    assert s2.review_state == "not_submitted"


# ─── can_review_transition ───────────────────────────────


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        ("not_submitted", "pending_review"),
        ("pending_review", "approved"),
        ("pending_review", "rejected"),
        ("rejected", "pending_review"),
    ],
)
def test_can_review_transition_legal(from_s, to_s):
    assert can_review_transition(from_s, to_s) is True


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        # 自转非法
        ("not_submitted", "not_submitted"),
        ("approved", "approved"),
        # approved 终态
        ("approved", "draft"),
        ("approved", "pending_review"),
        # not_submitted 不能直接 approved
        ("not_submitted", "approved"),
        ("not_submitted", "rejected"),
        # rejected 不能直接 approved / not_submitted
        ("rejected", "approved"),
        ("rejected", "not_submitted"),
    ],
)
def test_can_review_transition_illegal(from_s, to_s):
    assert can_review_transition(from_s, to_s) is False


# ─── submit_for_review ───────────────────────────────────


def test_submit_for_review_happy_from_not_submitted():
    skill = _make(status="draft", review_state="not_submitted")
    fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    out = submit_for_review(skill, user_id="u-author", note="ready", now=fixed)
    assert out.review_state == "pending_review"
    assert len(out.review_history) == 1
    r = out.review_history[0]
    assert r.action == "submit"
    assert r.reviewer_id == "u-author"
    assert r.note == "ready"
    assert out.updated_at == fixed
    assert out.last_reviewer_id is None  # submit 不更新 last_reviewer


def test_submit_for_review_happy_from_rejected():
    """作者修订后重提."""
    prev = ReviewRecord(
        reviewer_id="r-1",
        action="reject",
        timestamp=datetime(2026, 5, 30, tzinfo=timezone.utc),
        note="too generic",
    )
    skill = _make(
        status="draft", review_state="rejected",
        review_history=[prev],
        last_reviewer_id="r-1",
    )
    out = submit_for_review(skill, user_id="u-author", note="revised")
    assert out.review_state == "pending_review"
    assert len(out.review_history) == 2  # 保留旧 reject 记录


def test_submit_for_review_illegal_status():
    """非 draft 不能提交."""
    skill = _make(status="active", review_state="not_submitted")
    with pytest.raises(InvalidReviewTransition):
        submit_for_review(skill, user_id="u-author")


def test_submit_for_review_illegal_state():
    """pending_review / approved 不能重复 submit."""
    skill = _make(status="draft", review_state="pending_review")
    with pytest.raises(InvalidReviewTransition):
        submit_for_review(skill, user_id="u-author")


# ─── approve ─────────────────────────────────────────────


def test_approve_happy_transitions_status_to_active():
    submit_rec = ReviewRecord(
        reviewer_id="u-author",
        action="submit",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    skill = _make(
        status="draft", review_state="pending_review",
        review_history=[submit_rec],
    )
    fixed = datetime(2026, 6, 2, tzinfo=timezone.utc)
    out = approve(skill, reviewer_id="r-bob", note="LGTM", now=fixed)
    assert out.review_state == "approved"
    assert out.status == "active"  # ← 关键: 同步转 active
    assert out.last_reviewer_id == "r-bob"
    assert out.last_reviewed_at == fixed
    assert len(out.review_history) == 2
    assert out.review_history[-1].action == "approve"


def test_approve_illegal_non_pending():
    skill = _make(status="draft", review_state="not_submitted")
    with pytest.raises(InvalidReviewTransition):
        approve(skill, reviewer_id="r-bob")


def test_approve_requires_status_draft():
    """skill 不在 draft 状态时 (如手动转 active) 不允许 approve."""
    skill = _make(status="active", review_state="pending_review")
    with pytest.raises(InvalidReviewTransition):
        approve(skill, reviewer_id="r-bob")


# ─── reject ──────────────────────────────────────────────


def test_reject_happy_keeps_status_draft():
    submit_rec = ReviewRecord(
        reviewer_id="u-author",
        action="submit",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    skill = _make(
        status="draft", review_state="pending_review",
        review_history=[submit_rec],
    )
    out = reject(skill, reviewer_id="r-bob", reason="too generic")
    assert out.review_state == "rejected"
    assert out.status == "draft"  # 保留 draft
    assert out.last_reviewer_id == "r-bob"
    assert out.review_history[-1].note == "too generic"


def test_reject_requires_reason():
    skill = _make(status="draft", review_state="pending_review")
    with pytest.raises(InvalidReviewTransition):
        reject(skill, reviewer_id="r-bob", reason="")


def test_reject_illegal_non_pending():
    skill = _make(status="draft", review_state="not_submitted")
    with pytest.raises(InvalidReviewTransition):
        reject(skill, reviewer_id="r-bob", reason="why")


# ─── latest_review_record ────────────────────────────────


def test_latest_review_record_empty():
    skill = _make()
    assert latest_review_record(skill) is None


def test_latest_review_record_returns_last():
    r1 = ReviewRecord(
        reviewer_id="u",
        action="submit",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    r2 = ReviewRecord(
        reviewer_id="r",
        action="reject",
        timestamp=datetime(2026, 6, 2, tzinfo=timezone.utc),
        note="x",
    )
    skill = _make(review_history=[r1, r2])
    latest = latest_review_record(skill)
    assert latest is r2


# ─── 完整 cycle ─────────────────────────────────────────


def test_full_review_cycle_resubmit_after_reject():
    """draft submit → reject → 改 → submit → approve → active."""
    skill = _make(status="draft", review_state="not_submitted")
    skill = submit_for_review(skill, user_id="u-author")
    skill = reject(skill, reviewer_id="r-bob", reason="needs more examples")
    assert skill.review_state == "rejected"
    assert skill.status == "draft"

    # 作者改后重提
    skill = submit_for_review(skill, user_id="u-author", note="addressed")
    assert skill.review_state == "pending_review"
    assert len(skill.review_history) == 3

    # reviewer 批
    skill = approve(skill, reviewer_id="r-bob")
    assert skill.review_state == "approved"
    assert skill.status == "active"
    assert len(skill.review_history) == 4
