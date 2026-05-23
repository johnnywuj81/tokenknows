"""Skill 状态机 + Consent 字段 (v0.5.1 T48).

覆盖:
- SkillStatus 7 种 Literal 校验
- ConsentRecord 必填字段 + channel Literal
- 新 4 字段 default + 旧 JSON backfill
- can_transition 矩阵 (legal/illegal)
- initialize_pending: empty contributors / happy / idempotent / illegal status
- check_all_signed 边界
- apply_sign / apply_reject / mark_expired / is_expired
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.skill import ConsentRecord, Skill, SkillMetrics, SkillStatus
from app.services.skill.consent import (
    InvalidTransition,
    apply_reject,
    apply_sign,
    assert_can_transition,
    can_transition,
    check_all_signed,
    initialize_pending,
    is_expired,
    mark_expired,
)


# ─── Helpers ─────────────────────────────────────────────


def _make_skill(
    *,
    status: SkillStatus = "draft",
    contributors: list[str] | None = None,
    required: list[str] | None = None,
    signed: list[ConsentRecord] | None = None,
    rejected: ConsentRecord | None = None,
    expires_at: datetime | None = None,
) -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id="skill-test-1",
        project_id="proj-X",
        name="dummy",
        version=1,
        skill_md="---\nname: dummy\n---\n# body",
        embedding=None,
        metrics=SkillMetrics(),
        distilled_from=[],
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status=status,
        parent_skill_id=None,
        contributors=contributors or [],
        consent_required_from=required or [],
        consent_signed_by=signed or [],
        consent_rejected_by=rejected,
        consent_expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )


def _sign(uid: str, at: datetime | None = None) -> ConsentRecord:
    return ConsentRecord(
        user_id=uid,
        signed_at=at or datetime.now(timezone.utc),
        channel="web",
    )


# ─── SkillStatus Literal 校验 ────────────────────────────


@pytest.mark.parametrize(
    "status",
    [
        "draft", "active", "deprecated", "locked",
        "pending_contributor_consent",
        "rejected_by_contributor",
        "expired_no_consent",
    ],
)
def test_skill_status_all_7_literals_valid(status):
    skill = _make_skill(status=status)
    assert skill.status == status


def test_skill_status_invalid_string_rejected():
    with pytest.raises(ValidationError):
        _make_skill(status="totally_made_up")  # type: ignore[arg-type]


# ─── ConsentRecord ───────────────────────────────────────


def test_consent_record_required_fields():
    r = ConsentRecord(
        user_id="ou-a", signed_at=datetime.now(timezone.utc), channel="im_dm"
    )
    assert r.user_id == "ou-a"
    assert r.channel == "im_dm"
    assert r.note is None


def test_consent_record_channel_literal_strict():
    with pytest.raises(ValidationError):
        ConsentRecord(
            user_id="ou-a",
            signed_at=datetime.now(timezone.utc),
            channel="email",  # type: ignore[arg-type]
        )


# ─── 新字段 default + backfill ───────────────────────────


def test_new_consent_fields_default_empty():
    s = _make_skill()
    assert s.contributors == []
    assert s.consent_required_from == []
    assert s.consent_signed_by == []
    assert s.consent_rejected_by is None
    assert s.consent_expires_at is None


def test_old_skill_json_backfills_consent_fields():
    """v0.4 之前的 JSON 没有 consent 字段, load 时应自动填 default."""
    now = datetime.now(timezone.utc).isoformat()
    legacy_json = {
        "id": "skill-old-1",
        "project_id": "proj-X",
        "name": "legacy",
        "version": 1,
        "skill_md": "---\nname: legacy\n---\n# x",
        "embedding": None,
        "metrics": {
            "usage_count": 0, "acceptance_count": 0, "rejection_count": 0,
            "avg_acceptance_rate": 0.0, "trust_score": 0.5,
        },
        "distilled_from": [],
        "distilled_at": now,
        "last_used_at": None,
        "locked": False,
        "status": "active",
        "parent_skill_id": None,
        "created_at": now,
        "updated_at": now,
        # 注意: 无 contributors / consent_* 字段
    }
    s = Skill.model_validate(legacy_json)
    assert s.contributors == []
    assert s.consent_required_from == []
    assert s.consent_signed_by == []
    assert s.consent_rejected_by is None
    assert s.consent_expires_at is None
    # round-trip
    dumped = s.model_dump(mode="json")
    s2 = Skill.model_validate(dumped)
    assert s2.status == "active"


def test_consent_record_round_trip_via_json():
    record_at = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    s = _make_skill(
        status="pending_contributor_consent",
        contributors=["ou-a", "ou-b"],
        required=["ou-a", "ou-b"],
        signed=[ConsentRecord(user_id="ou-a", signed_at=record_at, channel="im_dm", note="ok")],
        expires_at=record_at + timedelta(days=30),
    )
    raw = json.loads(s.model_dump_json())
    s2 = Skill.model_validate(raw)
    assert len(s2.consent_signed_by) == 1
    assert s2.consent_signed_by[0].channel == "im_dm"
    assert s2.consent_signed_by[0].note == "ok"


# ─── can_transition 矩阵 ─────────────────────────────────


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        # pending → 3 出口
        ("pending_contributor_consent", "draft"),
        ("pending_contributor_consent", "rejected_by_contributor"),
        ("pending_contributor_consent", "expired_no_consent"),
        # draft → 3 出口
        ("draft", "active"),
        ("draft", "locked"),
        ("draft", "deprecated"),
        # active → 3 出口
        ("active", "locked"),
        ("active", "deprecated"),
        ("active", "draft"),
        # locked / rejected / expired → deprecated
        ("locked", "deprecated"),
        ("rejected_by_contributor", "deprecated"),
        ("expired_no_consent", "deprecated"),
    ],
)
def test_can_transition_legal(from_s, to_s):
    assert can_transition(from_s, to_s) is True


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        # 自转非法
        ("draft", "draft"),
        ("active", "active"),
        # pending 不能直接跳 active
        ("pending_contributor_consent", "active"),
        ("pending_contributor_consent", "locked"),
        # draft 不能直接到 pending (initialize_pending 才能)
        # 但 can_transition 矩阵不允许 (语义上 pending 是 distill 时的初始态)
        ("draft", "pending_contributor_consent"),
        # rejected 不能复活
        ("rejected_by_contributor", "active"),
        ("rejected_by_contributor", "draft"),
        # expired 同理
        ("expired_no_consent", "draft"),
        ("expired_no_consent", "active"),
        # locked 不能回 active (必须先 deprecated 再蒸新版)
        ("locked", "active"),
        ("locked", "draft"),
        # deprecated 是终态
        ("deprecated", "active"),
        ("deprecated", "draft"),
    ],
)
def test_can_transition_illegal(from_s, to_s):
    assert can_transition(from_s, to_s) is False


def test_assert_can_transition_raises():
    with pytest.raises(InvalidTransition):
        assert_can_transition("rejected_by_contributor", "active")


# ─── initialize_pending ──────────────────────────────────


def test_initialize_pending_empty_contributors_returns_original():
    """无 contributors → 跳过 consent, 保持 draft."""
    s = _make_skill(status="draft", contributors=[])
    out = initialize_pending(s)
    assert out is s  # 同对象
    assert out.status == "draft"
    assert out.consent_required_from == []
    assert out.consent_expires_at is None


def test_initialize_pending_happy_writes_required_and_expires():
    s = _make_skill(status="draft", contributors=["ou-a", "ou-b"])
    fixed_now = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    out = initialize_pending(s, now=fixed_now)
    assert out.status == "pending_contributor_consent"
    assert out.consent_required_from == ["ou-a", "ou-b"]
    assert out.consent_signed_by == []
    assert out.consent_rejected_by is None
    assert out.consent_expires_at == fixed_now + timedelta(days=30)
    assert out.updated_at == fixed_now
    # 原对象未被修改 (immutable)
    assert s.status == "draft"


def test_initialize_pending_idempotent_on_already_pending():
    """已经 pending → 不动 expires_at / signed_by."""
    fixed_expires = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    record = _sign("ou-a", at=datetime(2026, 5, 5, tzinfo=timezone.utc))
    s = _make_skill(
        status="pending_contributor_consent",
        contributors=["ou-a", "ou-b"],
        required=["ou-a", "ou-b"],
        signed=[record],
        expires_at=fixed_expires,
    )
    out = initialize_pending(s)
    assert out is s
    assert out.consent_expires_at == fixed_expires
    assert len(out.consent_signed_by) == 1


def test_initialize_pending_illegal_from_active_raises():
    s = _make_skill(status="active", contributors=["ou-a"])
    with pytest.raises(InvalidTransition):
        initialize_pending(s)


def test_initialize_pending_required_decoupled_from_contributors():
    """initialize 后改 contributors 不影响 required_from (已锁定)."""
    s = _make_skill(status="draft", contributors=["ou-a"])
    out = initialize_pending(s)
    # 模拟事后改 contributors (虽然实际不允许, 但确保 required 已独立 copy)
    out2 = out.model_copy(update={"contributors": ["ou-a", "ou-b"]})
    assert out2.consent_required_from == ["ou-a"]


# ─── check_all_signed ────────────────────────────────────


def test_check_all_signed_empty_required_returns_true():
    s = _make_skill(required=[])
    assert check_all_signed(s) is True


def test_check_all_signed_partial_returns_false():
    s = _make_skill(required=["ou-a", "ou-b"], signed=[_sign("ou-a")])
    assert check_all_signed(s) is False


def test_check_all_signed_full_returns_true():
    s = _make_skill(
        required=["ou-a", "ou-b"],
        signed=[_sign("ou-a"), _sign("ou-b")],
    )
    assert check_all_signed(s) is True


def test_check_all_signed_extra_signer_still_ok():
    """signed 含 required 外的人也 OK (软兼容)."""
    s = _make_skill(
        required=["ou-a"],
        signed=[_sign("ou-a"), _sign("ou-rogue")],
    )
    assert check_all_signed(s) is True


# ─── apply_sign ──────────────────────────────────────────


def test_apply_sign_happy_appends():
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a", "ou-b"],
    )
    r = _sign("ou-a")
    out = apply_sign(s, r)
    assert len(out.consent_signed_by) == 1
    assert out.consent_signed_by[0].user_id == "ou-a"
    assert out.status == "pending_contributor_consent"  # 不自动转
    assert s.consent_signed_by == []  # 原对象不动


def test_apply_sign_idempotent_same_user():
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a"],
        signed=[_sign("ou-a", at=datetime(2026, 5, 1, tzinfo=timezone.utc))],
    )
    r2 = _sign("ou-a", at=datetime(2026, 5, 2, tzinfo=timezone.utc))
    out = apply_sign(s, r2)
    assert len(out.consent_signed_by) == 1
    # 保留首次 signed_at
    assert out.consent_signed_by[0].signed_at == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_apply_sign_after_reject_raises():
    rejected = ConsentRecord(
        user_id="ou-b", signed_at=datetime.now(timezone.utc), channel="web"
    )
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a", "ou-b"],
        rejected=rejected,
    )
    # 注意: 一旦 rejected, status 通常已转 rejected_by_contributor
    # 这里测从 apply_reject 路径未走完的边界 (rejected_by 已写但 status 没改)
    with pytest.raises(InvalidTransition):
        apply_sign(s, _sign("ou-a"))


def test_apply_sign_on_non_pending_raises():
    s = _make_skill(status="draft")
    with pytest.raises(InvalidTransition):
        apply_sign(s, _sign("ou-a"))


# ─── apply_reject ────────────────────────────────────────


def test_apply_reject_freezes_skill():
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a", "ou-b"],
    )
    r = ConsentRecord(
        user_id="ou-a",
        signed_at=datetime.now(timezone.utc),
        channel="im_dm",
        note="not appropriate",
    )
    out = apply_reject(s, r)
    assert out.status == "rejected_by_contributor"
    assert out.consent_rejected_by is not None
    assert out.consent_rejected_by.user_id == "ou-a"
    assert out.consent_rejected_by.note == "not appropriate"


def test_apply_reject_idempotent_keeps_first_rejector():
    first = ConsentRecord(
        user_id="ou-a",
        signed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        channel="web",
    )
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a", "ou-b"],
        rejected=first,
    )
    second = ConsentRecord(
        user_id="ou-b",
        signed_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        channel="web",
    )
    # 已经被冻结, status 应该已经是 rejected_by_contributor;
    # 这里假设上层先调 reject 再继续 (apply_reject 拦上 status 检查会拒)
    # 因此构造仍 pending + rejected_by 已存的 race 场景:
    out = apply_reject(s, second)
    assert out is s  # 幂等不变
    assert out.consent_rejected_by.user_id == "ou-a"


def test_apply_reject_on_non_pending_raises():
    s = _make_skill(status="active")
    with pytest.raises(InvalidTransition):
        apply_reject(
            s,
            ConsentRecord(user_id="ou-a", signed_at=datetime.now(timezone.utc), channel="web"),
        )


# ─── mark_expired / is_expired ────────────────────────────


def test_is_expired_no_expires_at_returns_false():
    s = _make_skill(status="pending_contributor_consent")
    assert is_expired(s) is False


def test_is_expired_past_returns_true():
    s = _make_skill(
        status="pending_contributor_consent",
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert is_expired(s) is True


def test_is_expired_future_returns_false():
    s = _make_skill(
        status="pending_contributor_consent",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert is_expired(s) is False


def test_mark_expired_happy():
    s = _make_skill(
        status="pending_contributor_consent",
        required=["ou-a"],
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    out = mark_expired(s)
    assert out.status == "expired_no_consent"


def test_mark_expired_on_non_pending_raises():
    s = _make_skill(status="active")
    with pytest.raises(InvalidTransition):
        mark_expired(s)


# ─── 集成: 完整流程 ──────────────────────────────────────


def test_full_consent_flow_two_contributors_all_signed():
    """distill → initialize_pending → 两个 sign → check_all_signed True → 转 draft."""
    fixed = datetime(2026, 5, 1, tzinfo=timezone.utc)
    skill = _make_skill(status="draft", contributors=["ou-a", "ou-b"])

    pending = initialize_pending(skill, now=fixed)
    assert pending.status == "pending_contributor_consent"

    # 第一个 sign
    pending = apply_sign(pending, _sign("ou-a", at=fixed + timedelta(hours=1)))
    assert check_all_signed(pending) is False

    # 第二个 sign
    pending = apply_sign(pending, _sign("ou-b", at=fixed + timedelta(hours=2)))
    assert check_all_signed(pending) is True

    # endpoint 应转 draft
    assert can_transition(pending.status, "draft")
    final = pending.model_copy(update={"status": "draft"})
    assert final.status == "draft"


def test_full_consent_flow_one_reject_kills_skill():
    skill = _make_skill(status="draft", contributors=["ou-a", "ou-b"])
    pending = initialize_pending(skill)

    pending = apply_sign(pending, _sign("ou-a"))
    pending = apply_reject(
        pending,
        ConsentRecord(
            user_id="ou-b",
            signed_at=datetime.now(timezone.utc),
            channel="im_dm",
            note="敏感讨论",
        ),
    )
    assert pending.status == "rejected_by_contributor"
    assert pending.consent_rejected_by.user_id == "ou-b"
    # 不能复活
    assert not can_transition(pending.status, "draft")
    assert not can_transition(pending.status, "active")
    # 只能归档
    assert can_transition(pending.status, "deprecated")
