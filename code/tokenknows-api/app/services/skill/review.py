"""Skill Reviewer 审批流 · v0.6.0 T56.

把 Skill 从 draft 推到 active 的正式闸门. 与 contributor consent (T48-T50)
正交 (用 review_state 字段; status 仅在 approve 时由 draft 同步转 active).

状态转换 (review_state):
  not_submitted → pending_review     (submit_for_review)
  pending_review → approved          (reviewer approve, 同时 status draft→active)
  pending_review → rejected          (reviewer reject)
  rejected → pending_review          (作者修订后重提)
  approved → 终态                    (想改先 status active→draft 走新一轮)

设计原则:
- 纯函数: 接收 Skill 返回新 Skill (immutable; model_copy(update=...))
- 配合 endpoint (T57) 调; service 不写库, 调用方负责持久化
- 历史保留: 每次 submit/approve/reject 都 append ReviewRecord 到 history
- reviewer 不能审自己 contributors (利益相关) - 由 endpoint 业务层校验
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.skill import ReviewRecord, ReviewState, Skill


class InvalidReviewTransition(ValueError):
    """非法的 review_state 转换."""


# review_state → 允许 to 集合.
# submit_for_review 是入口, 不在此矩阵 (它有独立校验).
_REVIEW_TRANSITIONS: dict[ReviewState, set[ReviewState]] = {
    "not_submitted": {"pending_review"},
    "pending_review": {"approved", "rejected"},
    "approved": set(),  # 终态
    "rejected": {"pending_review"},  # 作者重提
}


def can_review_transition(
    from_state: ReviewState, to_state: ReviewState
) -> bool:
    if from_state == to_state:
        return False
    return to_state in _REVIEW_TRANSITIONS.get(from_state, set())


def submit_for_review(
    skill: Skill,
    *,
    user_id: str,
    note: str | None = None,
    now: datetime | None = None,
) -> Skill:
    """作者提交 skill 等待 reviewer 审批.

    前置:
    - skill.status == 'draft' (consent 已通过 / 手动蒸馏的 draft)
    - review_state ∈ {not_submitted, rejected}

    Raises:
        InvalidReviewTransition: 状态不符
    """
    if skill.status != "draft":
        raise InvalidReviewTransition(
            f"submit_for_review only on status=draft, got {skill.status}"
        )
    if skill.review_state not in ("not_submitted", "rejected"):
        raise InvalidReviewTransition(
            f"submit_for_review only from not_submitted/rejected, "
            f"got review_state={skill.review_state}"
        )

    now_utc = now or datetime.now(timezone.utc)
    record = ReviewRecord(
        reviewer_id=user_id,  # submit 时 actor 就是作者本人
        action="submit",
        timestamp=now_utc,
        note=note,
    )
    return skill.model_copy(
        update={
            "review_state": "pending_review",
            "review_history": [*skill.review_history, record],
            "updated_at": now_utc,
            # last_reviewer_id 不更新 (submit 不是 review 决定)
        }
    )


def approve(
    skill: Skill,
    *,
    reviewer_id: str,
    note: str | None = None,
    now: datetime | None = None,
) -> Skill:
    """Reviewer 批准: review_state=approved + status draft→active.

    前置: review_state == pending_review.
    """
    if skill.review_state != "pending_review":
        raise InvalidReviewTransition(
            f"approve only on pending_review, got {skill.review_state}"
        )
    # status 必须仍是 draft (不允许 active/locked/deprecated 上跑审批)
    if skill.status != "draft":
        raise InvalidReviewTransition(
            f"approve requires status=draft, got {skill.status}"
        )

    now_utc = now or datetime.now(timezone.utc)
    record = ReviewRecord(
        reviewer_id=reviewer_id,
        action="approve",
        timestamp=now_utc,
        note=note,
    )
    return skill.model_copy(
        update={
            "review_state": "approved",
            "status": "active",  # 自动转 active
            "review_history": [*skill.review_history, record],
            "last_reviewer_id": reviewer_id,
            "last_reviewed_at": now_utc,
            "updated_at": now_utc,
        }
    )


def reject(
    skill: Skill,
    *,
    reviewer_id: str,
    reason: str,
    now: datetime | None = None,
) -> Skill:
    """Reviewer 拒绝: review_state=rejected, status 保持 draft.

    作者可修订后再 submit_for_review (再走一轮).

    前置: review_state == pending_review.
    """
    if skill.review_state != "pending_review":
        raise InvalidReviewTransition(
            f"reject only on pending_review, got {skill.review_state}"
        )
    if not reason or not reason.strip():
        raise InvalidReviewTransition("reject reason required")

    now_utc = now or datetime.now(timezone.utc)
    record = ReviewRecord(
        reviewer_id=reviewer_id,
        action="reject",
        timestamp=now_utc,
        note=reason.strip(),
    )
    return skill.model_copy(
        update={
            "review_state": "rejected",
            "review_history": [*skill.review_history, record],
            "last_reviewer_id": reviewer_id,
            "last_reviewed_at": now_utc,
            "updated_at": now_utc,
        }
    )


def latest_review_record(skill: Skill) -> ReviewRecord | None:
    """取最新一条 ReviewRecord (UI 显示决策来源)."""
    if not skill.review_history:
        return None
    return skill.review_history[-1]


__all__ = [
    "InvalidReviewTransition",
    "approve",
    "can_review_transition",
    "latest_review_record",
    "reject",
    "submit_for_review",
]
