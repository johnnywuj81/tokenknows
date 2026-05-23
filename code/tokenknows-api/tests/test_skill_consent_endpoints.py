"""T50 · Skill Consent Endpoints + Sweep job.

覆盖:
- sign endpoint:
  * 404 skill 不存在
  * 409 status 非 pending
  * 403 user 不在 required_from
  * happy (单人签 → 仍 pending)
  * happy 全签 → 自动转 draft
  * 幂等 (同 user 重复 sign)
- reject endpoint:
  * 404 / 409 / 403
  * happy 冻结
- sweep_expired_consents:
  * 跳过未到期
  * 转 expired
  * try-except per skill (单条失败不阻断)
- consent_sweep_expired_job
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.gateway.http_api.skills import router as skills_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import Skill, SkillMetrics
from app.services import skill_service
from app.services.skill import consent as skill_consent
from app.services.skill.consent import (
    InvalidTransition,
    initialize_pending,
    reject_consent,
    sign_consent,
    sweep_expired_consents,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    skill_service.reset_registry_for_tests()
    return s


@pytest.fixture
def client(fresh_db) -> TestClient:
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(skills_router)
    return TestClient(app)


def _seed_pending_skill(
    *, contributors=("ou-a", "ou-b"), expires_in_days: float | None = None
) -> Skill:
    now = datetime.now(timezone.utc)
    skill = Skill(
        id="skill-e2e-1",
        project_id="proj-X",
        name="im-distilled-e2e",
        version=1,
        skill_md="---\nname: im\n---\n# body",
        embedding=None,
        metrics=SkillMetrics(),
        distilled_from=[],
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status="draft",
        parent_skill_id=None,
        contributors=list(contributors),
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    skill = initialize_pending(skill)
    if expires_in_days is not None:
        skill = skill.model_copy(
            update={
                "consent_expires_at": now + timedelta(days=expires_in_days)
            }
        )
    skill_service.get_registry().add(skill)
    return skill


# ─── sign endpoint ────────────────────────────────────────


def test_sign_endpoint_404_not_found(client):
    r = client.post(
        "/skills/skill-nope/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r.status_code == 404


def test_sign_endpoint_409_non_pending(client, fresh_db):
    skill = _seed_pending_skill()
    # 强行改成 active
    skill_service.get_registry().update(
        skill.model_copy(update={"status": "active"})
    )
    r = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r.status_code == 409
    assert "pending" in r.json()["detail"]


def test_sign_endpoint_403_user_not_in_required(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    r = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-rogue", "channel": "web"},
    )
    assert r.status_code == 403


def test_sign_endpoint_happy_single_still_pending(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    r = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web", "note": "ok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["current_status"] == "pending_contributor_consent"
    assert body["signed_count"] == 1
    assert body["required_count"] == 2
    assert body["all_signed"] is False


def test_sign_endpoint_happy_full_signed_transitions_to_draft(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    r1 = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-b", "channel": "im_dm"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["current_status"] == "draft"  # 全签转 draft
    assert body["all_signed"] is True
    # 真转了
    refreshed = skill_service.get_skill(skill.id)
    assert refreshed.status == "draft"


def test_sign_endpoint_idempotent_same_user(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    r1 = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r1.json()["signed_count"] == 1
    r2 = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    # 第二次仍 200, 但 signed_count 还是 1
    assert r2.status_code == 200
    assert r2.json()["signed_count"] == 1


def test_sign_endpoint_followup_notifies_others(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b", "ou-c"))
    client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    # ou-b / ou-c 应各收到一条 consent_signed 通知
    b_notifs = fresh_db.list_notifications_for_user("ou-b")
    assert any(n["type"] == "consent_signed" for n in b_notifs)
    c_notifs = fresh_db.list_notifications_for_user("ou-c")
    assert any(n["type"] == "consent_signed" for n in c_notifs)
    # ou-a 自己不收到自己的
    a_notifs = fresh_db.list_notifications_for_user("ou-a")
    assert not any(n["type"] == "consent_signed" for n in a_notifs)


# ─── reject endpoint ──────────────────────────────────────


def test_reject_endpoint_404(client):
    r = client.post(
        "/skills/skill-nope/consent/reject",
        json={"user_id": "ou-a", "channel": "web", "reason": "..."},
    )
    assert r.status_code == 404


def test_reject_endpoint_409_non_pending(client, fresh_db):
    skill = _seed_pending_skill()
    skill_service.get_registry().update(
        skill.model_copy(update={"status": "active"})
    )
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={"user_id": "ou-a", "channel": "web", "reason": "no"},
    )
    assert r.status_code == 409


def test_reject_endpoint_403_user_not_in_required(client, fresh_db):
    skill = _seed_pending_skill()
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={"user_id": "ou-rogue", "channel": "web", "reason": "nope"},
    )
    assert r.status_code == 403


def test_reject_endpoint_happy_freezes_skill(client, fresh_db):
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={
            "user_id": "ou-b",
            "channel": "web",
            "reason": "属于 HR 讨论, 不宜蒸馏到项目知识库",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["current_status"] == "rejected_by_contributor"
    assert body["rejected_by"] == "ou-b"
    refreshed = skill_service.get_skill(skill.id)
    assert refreshed.status == "rejected_by_contributor"
    assert refreshed.consent_rejected_by.user_id == "ou-b"
    assert refreshed.consent_rejected_by.note.startswith("属于 HR")


def test_reject_endpoint_reason_required(client, fresh_db):
    skill = _seed_pending_skill()
    # Pydantic 强制 reason min_length=1
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={"user_id": "ou-a", "channel": "web"},  # 缺 reason
    )
    assert r.status_code == 422


def test_reject_after_some_sign_still_freezes(client, fresh_db):
    """ou-a 签 → ou-b 拒 → 仍然 rejected (单否决)."""
    skill = _seed_pending_skill(contributors=("ou-a", "ou-b"))
    client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={"user_id": "ou-b", "channel": "web", "reason": "no"},
    )
    assert r.status_code == 200
    assert r.json()["current_status"] == "rejected_by_contributor"

    # 之后 sign 已经无效 (skill 不再 pending)
    r3 = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r3.status_code == 409


# ─── consent.py 纯函数 ────────────────────────────────────


def test_sign_consent_helper_invalid_status():
    from app.schemas.skill import Skill, SkillMetrics
    now = datetime.now(timezone.utc)
    skill = Skill(
        id="x", project_id="p", name="n", version=1,
        skill_md="---\n---\n", metrics=SkillMetrics(),
        distilled_from=[], distilled_at=now,
        status="active",
        consent_required_from=["ou-a"],
        created_at=now, updated_at=now,
    )
    with pytest.raises(InvalidTransition):
        sign_consent(skill, user_id="ou-a")


def test_reject_consent_helper_invalid_status():
    from app.schemas.skill import Skill, SkillMetrics
    now = datetime.now(timezone.utc)
    skill = Skill(
        id="x", project_id="p", name="n", version=1,
        skill_md="---\n---\n", metrics=SkillMetrics(),
        distilled_from=[], distilled_at=now,
        status="draft",
        consent_required_from=["ou-a"],
        created_at=now, updated_at=now,
    )
    with pytest.raises(InvalidTransition):
        reject_consent(skill, user_id="ou-a", reason="no")


# ─── sweep_expired_consents ───────────────────────────────


def test_sweep_skip_not_expired(fresh_db):
    skill = _seed_pending_skill(expires_in_days=10.0)  # 10 天后到期
    result = sweep_expired_consents()
    assert result["expired"] == 0
    assert result["scanned"] == 1
    refreshed = skill_service.get_skill(skill.id)
    assert refreshed.status == "pending_contributor_consent"


def test_sweep_marks_expired_past(fresh_db):
    skill = _seed_pending_skill(expires_in_days=-1.0)  # 已过期
    result = sweep_expired_consents()
    assert result["expired"] == 1
    refreshed_dict = fresh_db.get_skill(skill.id)
    assert refreshed_dict["status"] == "expired_no_consent"


def test_sweep_skips_non_pending(fresh_db):
    """rejected / active skill 不应被扫."""
    skill = _seed_pending_skill(expires_in_days=-1.0)
    # 强转 rejected_by_contributor
    rejected = skill.model_copy(update={"status": "rejected_by_contributor"})
    fresh_db.upsert_skill(
        skill_id=rejected.id,
        project_id=rejected.project_id,
        name=rejected.name,
        version=rejected.version,
        status=rejected.status,
        trust_score=rejected.metrics.trust_score,
        updated_at=rejected.updated_at.isoformat(),
        json_str=rejected.model_dump_json(),
    )
    result = sweep_expired_consents()
    assert result["expired"] == 0


def test_sweep_writes_followup_notifications(fresh_db):
    skill = _seed_pending_skill(
        contributors=("ou-a", "ou-b"), expires_in_days=-1.0
    )
    sweep_expired_consents()
    a_notifs = fresh_db.list_notifications_for_user("ou-a")
    assert any(n["type"] == "consent_expired" for n in a_notifs)


def test_sweep_handles_per_skill_errors(fresh_db, monkeypatch):
    """单条 skill 反序列化失败不阻断其他."""
    skill_good = _seed_pending_skill(
        contributors=("ou-a",), expires_in_days=-1.0
    )
    # 手工塞一条坏 JSON
    fresh_db._exec(
        """
        INSERT INTO skills (id, project_id, name, version, status,
                           trust_score, updated_at, json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "skill-bad", "proj-X", "bad", 1,
            "pending_contributor_consent", 0.5,
            datetime.now(timezone.utc).isoformat(),
            "not valid json {{{",
        ),
    )
    result = sweep_expired_consents()
    assert result["expired"] >= 1  # good 那条 expired
    assert result["errors"] >= 1   # bad 那条计入 errors


# ─── consent_sweep_expired_job ────────────────────────────


@pytest.mark.asyncio
async def test_consent_sweep_expired_job_runs(fresh_db):
    from app.services.auto_trigger.jobs import consent_sweep_expired_job
    _seed_pending_skill(expires_in_days=-2.0)
    # 不应抛异常
    await consent_sweep_expired_job()


@pytest.mark.asyncio
async def test_consent_sweep_expired_job_swallow_inner_errors(monkeypatch):
    from app.services.auto_trigger import jobs

    def _raise():
        raise RuntimeError("boom")
    monkeypatch.setattr(
        "app.services.skill.consent.sweep_expired_consents", _raise
    )
    # 不应抛
    await jobs.consent_sweep_expired_job()


# ─── scheduler 注册检查 ───────────────────────────────────


def test_scheduler_registers_consent_sweep_job():
    """job id 'consent_sweep_expired' 应在 _register_fixed_jobs 后存在."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.services.auto_trigger.scheduler import _register_fixed_jobs

    sched = AsyncIOScheduler()
    _register_fixed_jobs(sched)
    job = sched.get_job("consent_sweep_expired")
    assert job is not None
    assert "Skill consent 超时清理" in job.name
