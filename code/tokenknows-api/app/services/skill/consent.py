"""Skill Contributor Consent · v0.5.1 T48.

实现 Q5 决策的状态机闸门:
- `initialize_pending(skill)` 把刚自动蒸馏出的 skill 从 active/draft 截下来
  转 pending_contributor_consent, 写 required_from + expires_at
- `can_transition(from, to)` 7 状态合法转换矩阵 (见 task doc §3)
- `check_all_signed(skill)` 边界: required=[] → True
- `apply_sign(skill, record)` / `apply_reject(skill, record)` 纯函数 helper
  (实际 endpoint 调用, 见 T50)

设计原则:
- 纯函数 (无 DB 副作用), 接收 + 返回 Skill (immutable 风格)
- consent_required_from 在 initialize_pending **之后**不可修改
- 拒绝单否决 (首位 reject 冻结整个 skill, 后续 sign 无效)
- 时区一律 UTC; expires_at 由 daily sweep 检查
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from app.schemas.skill import ConsentRecord, Skill, SkillStatus


# OD-6: 30 天无人响应 → 自动 expired.
_CONSENT_WINDOW_DAYS = 30


class InvalidTransition(ValueError):
    """状态机非法转换 (Skill.status 从 X 不可直接跳 Y)."""


# ─── 转换矩阵 ────────────────────────────────────────────────────


# from_status → allowed to_status 集合 (其余非法).
# 见 task T48 §3:
#   pending → draft  (全员签)
#   pending → rejected_by_contributor  (任一拒)
#   pending → expired_no_consent  (sweep)
#   draft → active / locked / deprecated
#   active → locked / deprecated / draft (人工降级)
#   locked → deprecated  (固化版本归档)
#   rejected_by_contributor / expired_no_consent → deprecated (仅归档)
#   deprecated → 终态
_TRANSITIONS: dict[SkillStatus, set[SkillStatus]] = {
    "pending_contributor_consent": {
        "draft",
        "rejected_by_contributor",
        "expired_no_consent",
    },
    "draft": {"active", "locked", "deprecated"},
    "active": {"locked", "deprecated", "draft"},
    "locked": {"deprecated"},
    "rejected_by_contributor": {"deprecated"},
    "expired_no_consent": {"deprecated"},
    "deprecated": set(),  # 终态
}


def can_transition(from_status: SkillStatus, to_status: SkillStatus) -> bool:
    """是否允许从 from_status 转到 to_status.

    自转 (from == to) 视为非法 (避免无意义 update).
    """
    if from_status == to_status:
        return False
    return to_status in _TRANSITIONS.get(from_status, set())


def assert_can_transition(
    from_status: SkillStatus, to_status: SkillStatus
) -> None:
    """异常版本: 非法则抛 InvalidTransition (供 endpoint / sweep 调用)."""
    if not can_transition(from_status, to_status):
        raise InvalidTransition(
            f"illegal skill status transition: {from_status} → {to_status}"
        )


# ─── 初始化 pending ──────────────────────────────────────────────


def initialize_pending(skill: Skill, *, now: datetime | None = None) -> Skill:
    """把刚蒸馏出来 (status=draft, contributors 非空) 的 skill 转 pending.

    用法 (T49 在 dispatcher._dispatch_skill_distill 调):
        skill = await distill_skill(...)
        if skill.contributors:
            skill = initialize_pending(skill)
            # 保存 + 发通知

    边界:
    - contributors 为空: 跳过 (返回原 skill, 上层应保持 status=draft)
    - 已经是 pending_contributor_consent: 幂等 (不改 expires_at)
    - 其他 status (active/locked/...): 抛 InvalidTransition

    Returns:
        新 Skill 副本 (Pydantic model_copy(update=...))
    """
    if not skill.contributors:
        # 无 contributors → 跳过 consent 流程 (保持 draft).
        return skill

    if skill.status == "pending_contributor_consent":
        # 幂等: 不重置 expires_at, 不动 signed_by.
        return skill

    # 仅允许从 draft (distill_skill 默认) 进 pending.
    if skill.status != "draft":
        raise InvalidTransition(
            f"initialize_pending only from draft, got {skill.status}"
        )

    now_utc = now or datetime.now(timezone.utc)
    return skill.model_copy(
        update={
            "status": "pending_contributor_consent",
            "consent_required_from": list(skill.contributors),
            "consent_signed_by": [],
            "consent_rejected_by": None,
            "consent_expires_at": now_utc + timedelta(days=_CONSENT_WINDOW_DAYS),
            "updated_at": now_utc,
        }
    )


# ─── 签字 / 拒绝 / 检查 ──────────────────────────────────────────


def check_all_signed(skill: Skill) -> bool:
    """所有 required contributor 是否已签.

    边界:
    - required_from = [] → True (无人需签, 视为同意)
    - signed_by 中存在不在 required_from 的人也视为合法 (兼容历史扩边)
    """
    required = set(skill.consent_required_from)
    if not required:
        return True
    signed_ids = {r.user_id for r in skill.consent_signed_by}
    return required.issubset(signed_ids)


def apply_sign(skill: Skill, record: ConsentRecord) -> Skill:
    """一个 contributor 签字; 返回更新后的 skill.

    幂等: 同 user_id 重复签只保留第一次 (避免覆盖原 channel/note).
    非 required_from 中的 user_id 也允许签 (软兼容), 但不会推进 check_all_signed.
    全员签后调用方负责再用 `can_transition` 转 draft (避免本函数自动跨多状态).
    """
    if skill.status not in ("pending_contributor_consent",):
        raise InvalidTransition(
            f"apply_sign only on pending, got {skill.status}"
        )
    if skill.consent_rejected_by is not None:
        # 已经被否决, sign 无效 (避免 race).
        raise InvalidTransition("skill already rejected by a contributor")

    signed_ids = {r.user_id for r in skill.consent_signed_by}
    if record.user_id in signed_ids:
        return skill  # 幂等

    new_signed = [*skill.consent_signed_by, record]
    return skill.model_copy(
        update={
            "consent_signed_by": new_signed,
            "updated_at": record.signed_at,
        }
    )


def apply_reject(skill: Skill, record: ConsentRecord) -> Skill:
    """一个 contributor 拒绝; 冻结到 rejected_by_contributor (单否决原则).

    幂等: 已经被拒 → 保持原值 (不覆盖首位拒绝者).
    """
    if skill.status not in ("pending_contributor_consent",):
        raise InvalidTransition(
            f"apply_reject only on pending, got {skill.status}"
        )
    if skill.consent_rejected_by is not None:
        return skill  # 首位拒绝者已冻结
    return skill.model_copy(
        update={
            "status": "rejected_by_contributor",
            "consent_rejected_by": record,
            "updated_at": record.signed_at,
        }
    )


def mark_expired(skill: Skill, *, now: datetime | None = None) -> Skill:
    """daily sweep 用: 超时未签 → 转 expired_no_consent.

    调用方应先用 `is_expired` 或自己判 now > expires_at 再调.
    """
    if skill.status != "pending_contributor_consent":
        raise InvalidTransition(
            f"mark_expired only on pending, got {skill.status}"
        )
    return skill.model_copy(
        update={
            "status": "expired_no_consent",
            "updated_at": now or datetime.now(timezone.utc),
        }
    )


def is_expired(skill: Skill, *, now: datetime | None = None) -> bool:
    """sweep 辅助: 是否超 consent_expires_at."""
    if skill.consent_expires_at is None:
        return False
    return (now or datetime.now(timezone.utc)) > skill.consent_expires_at


# ─── Sweep (T50 daily 03:00) ──────────────────────────────────────


def sweep_expired_consents(*, now: datetime | None = None) -> dict[str, int]:
    """扫所有 status='pending_contributor_consent' 且 expires_at < now 的 skill,
    转 expired_no_consent + 通知 contributors.

    每天 03:00 由 APScheduler 调; 单条失败 try/except, 不阻塞下一条.

    Returns:
        {'expired': N, 'errors': M, 'scanned': S}
    """
    from app.persistence import store as store_module

    # 延迟 import 避免 consent.py ↔ consent_notifier 循环
    from app.services.im import consent_notifier as _notifier

    now_utc = now or datetime.now(timezone.utc)
    db = store_module.get_db()

    rows = db._query(  # noqa: SLF001 - sweep 内部用, 不暴露 API
        """
        SELECT json FROM skills
        WHERE status = ?
        """,
        ("pending_contributor_consent",),
    )
    expired = 0
    errors = 0
    scanned = len(rows)
    for r in rows:
        try:
            import json as _json
            skill_dict = _json.loads(r["json"])
            skill = Skill.model_validate(skill_dict)
            if not is_expired(skill, now=now_utc):
                continue
            new_skill = mark_expired(skill, now=now_utc)
            db.upsert_skill(
                skill_id=new_skill.id,
                project_id=new_skill.project_id,
                name=new_skill.name,
                version=new_skill.version,
                status=new_skill.status,
                trust_score=new_skill.metrics.trust_score,
                updated_at=new_skill.updated_at.isoformat(),
                json_str=new_skill.model_dump_json(),
            )
            # 回执通知 (web only, 不 IM 噪音)
            try:
                _notifier.notify_followup(
                    new_skill,
                    type_="consent_expired",
                    recipient_user_ids=new_skill.consent_required_from,
                )
            except Exception:  # noqa: BLE001
                pass
            expired += 1
        except Exception:  # noqa: BLE001
            errors += 1

    return {"expired": expired, "errors": errors, "scanned": scanned}


# ─── 高层 helper: 给 endpoint 用 ─────────────────────────────────


def sign_consent(
    skill: Skill,
    *,
    user_id: str,
    channel: Literal["im_dm", "web"] = "web",
    note: str | None = None,
    now: datetime | None = None,
) -> tuple[Skill, bool]:
    """同意闭环 helper (供 T50 endpoint 调).

    Args:
        skill: 当前 Skill 实例 (status 必须 pending)
        user_id: 签字者 platform user_id
        channel / note: 来源元数据
        now: 测试用 freeze; 默认 utcnow

    Returns:
        (updated_skill, all_signed):
        - updated_skill: 应用 sign 后的 Skill (若全员签则已转 draft)
        - all_signed: 是否全员签 + 已转 draft

    Raises:
        InvalidTransition: skill 非 pending / 已 rejected / user_id 不在 required_from
    """
    if skill.status != "pending_contributor_consent":
        raise InvalidTransition(
            f"sign_consent only on pending, got {skill.status}"
        )
    if user_id not in skill.consent_required_from:
        raise InvalidTransition(
            f"user {user_id} not in consent_required_from"
        )
    record = ConsentRecord(
        user_id=user_id,
        signed_at=now or datetime.now(timezone.utc),
        channel=channel,
        note=note,
    )
    new_skill = apply_sign(skill, record)
    if check_all_signed(new_skill):
        # 自动转 draft (T50 §7 spec)
        assert_can_transition(new_skill.status, "draft")
        new_skill = new_skill.model_copy(
            update={"status": "draft", "updated_at": record.signed_at}
        )
        return new_skill, True
    return new_skill, False


def reject_consent(
    skill: Skill,
    *,
    user_id: str,
    channel: Literal["im_dm", "web"] = "web",
    reason: str,
    now: datetime | None = None,
) -> Skill:
    """拒绝闭环 helper.

    Args:
        skill: 当前 pending skill
        user_id: 拒绝者
        reason: 必填理由 (≤ 500 字; 此处不强制截断, endpoint 层 Pydantic 控)

    Raises:
        InvalidTransition: 非 pending / 已 rejected / user 不在 required_from
    """
    if skill.status != "pending_contributor_consent":
        raise InvalidTransition(
            f"reject_consent only on pending, got {skill.status}"
        )
    if user_id not in skill.consent_required_from:
        raise InvalidTransition(
            f"user {user_id} not in consent_required_from"
        )
    record = ConsentRecord(
        user_id=user_id,
        signed_at=now or datetime.now(timezone.utc),
        channel=channel,
        note=reason,
    )
    return apply_reject(skill, record)


__all__ = [
    "InvalidTransition",
    "apply_reject",
    "apply_sign",
    "assert_can_transition",
    "can_transition",
    "check_all_signed",
    "initialize_pending",
    "is_expired",
    "mark_expired",
    "reject_consent",
    "sign_consent",
    "sweep_expired_consents",
]
