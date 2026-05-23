"""T57 · Skill Review endpoints + 通知.

覆盖:
- GET /projects/:id/skills/pending-review (Inbox)
- POST /skills/:id/submit-for-review (404/409/happy)
- POST /skills/:id/review/approve (404/409/happy + status 转 active)
- POST /skills/:id/review/reject (404/409/happy + reason 必填)
- 通知: submit → reviewer 收 web + SSE; approve/reject → 作者收
- 完整 cycle: submit → reject → 重提 → approve
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.skills import router as skills_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import Skill, SkillMetrics
from app.services import notification_sse, skill_service
from app.services.notification_sse import reset_for_tests, subscribe


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    skill_service.reset_registry_for_tests()
    return s


@pytest.fixture(autouse=True)
def reset_sse():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def client(fresh_db) -> TestClient:
    app = FastAPI()
    app.include_router(skills_router)
    return TestClient(app)


def _seed_draft(
    *,
    skill_id="skill-rv-1",
    project_id="proj-X",
    contributors=("u-author", "u-bob", "u-carol"),
) -> Skill:
    now = datetime.now(timezone.utc)
    skill = Skill(
        id=skill_id,
        project_id=project_id,
        name="im-distilled-review",
        version=1,
        skill_md="---\n---\n",
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
        review_state="not_submitted",
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )
    skill_service.get_registry().add(skill)
    return skill


# ─── GET pending-review ──────────────────────────────────


def test_pending_review_inbox_empty(client, fresh_db):
    r = client.get("/projects/proj-X/skills/pending-review")
    assert r.status_code == 200
    assert r.json() == []


def test_pending_review_inbox_filters_state(client, fresh_db):
    _seed_draft(skill_id="s-1")  # not_submitted
    s2 = _seed_draft(skill_id="s-2")
    # 手工转 s2 to pending_review
    s2 = s2.model_copy(update={"review_state": "pending_review"})
    skill_service.get_registry().update(s2)
    r = client.get("/projects/proj-X/skills/pending-review")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == "s-2"


# ─── POST submit-for-review ──────────────────────────────


def test_submit_404(client):
    r = client.post(
        "/skills/s-nope/submit-for-review",
        json={"user_id": "u-author"},
    )
    assert r.status_code == 404


def test_submit_409_non_draft(client, fresh_db):
    skill = _seed_draft()
    skill = skill.model_copy(update={"status": "active"})
    skill_service.get_registry().update(skill)
    r = client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    assert r.status_code == 409


def test_submit_happy_transitions_to_pending_review(client, fresh_db):
    skill = _seed_draft()
    r = client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author", "note": "ready"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["review_state"] == "pending_review"
    assert body["status"] == "draft"  # status 不变
    assert body["last_action"] == "submit"
    # 持久化校验
    persisted = skill_service.get_skill(skill.id)
    assert persisted.review_state == "pending_review"
    assert len(persisted.review_history) == 1


def test_submit_notifies_other_contributors(client, fresh_db):
    skill = _seed_draft(contributors=("u-author", "u-bob", "u-carol"))
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    # u-bob / u-carol 应收 web notification
    bob_notifs = fresh_db.list_notifications_for_user("u-bob")
    carol_notifs = fresh_db.list_notifications_for_user("u-carol")
    author_notifs = fresh_db.list_notifications_for_user("u-author")
    assert any(n["type"] == "skill_review_request" for n in bob_notifs)
    assert any(n["type"] == "skill_review_request" for n in carol_notifs)
    # 作者不应收到自己 submit 的通知
    assert not any(n["type"] == "skill_review_request" for n in author_notifs)


# ─── POST review/approve ─────────────────────────────────


def test_approve_409_not_pending(client, fresh_db):
    skill = _seed_draft()  # review_state=not_submitted
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "u-bob"},
    )
    assert r.status_code == 409


def test_approve_happy_promotes_to_active(client, fresh_db):
    skill = _seed_draft()
    # 先提交
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    # 批准
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "u-bob", "note": "LGTM"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["review_state"] == "approved"
    assert body["status"] == "active"  # ← 关键: 自动转 active
    assert body["last_reviewer_id"] == "u-bob"
    assert body["last_reviewed_at"] is not None

    persisted = skill_service.get_skill(skill.id)
    assert persisted.status == "active"
    assert persisted.review_state == "approved"


def test_approve_notifies_author(client, fresh_db):
    skill = _seed_draft()
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    # 清掉 submit 阶段写给 reviewer 的通知, 只看 approve 给作者的
    fresh_db.mark_all_notifications_read("u-bob")
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "u-bob"},
    )
    assert r.status_code == 200
    author_notifs = fresh_db.list_notifications_for_user("u-author")
    approved = [n for n in author_notifs if n["type"] == "skill_review_approved"]
    assert len(approved) == 1


# ─── POST review/reject ──────────────────────────────────


def test_reject_409_not_pending(client, fresh_db):
    skill = _seed_draft()
    r = client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "u-bob", "reason": "no"},
    )
    assert r.status_code == 409


def test_reject_reason_required(client, fresh_db):
    skill = _seed_draft()
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    r = client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "u-bob"},  # 缺 reason
    )
    assert r.status_code == 422


def test_reject_happy_keeps_draft(client, fresh_db):
    skill = _seed_draft()
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    r = client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "u-bob", "reason": "needs more concrete examples"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["review_state"] == "rejected"
    assert body["status"] == "draft"
    persisted = skill_service.get_skill(skill.id)
    assert persisted.status == "draft"
    assert persisted.review_state == "rejected"


def test_reject_notifies_author_with_reason(client, fresh_db):
    skill = _seed_draft()
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "u-bob", "reason": "too generic"},
    )
    author_notifs = fresh_db.list_notifications_for_user("u-author")
    rejected = [n for n in author_notifs if n["type"] == "skill_review_rejected"]
    assert len(rejected) == 1
    assert "too generic" in rejected[0]["body"]


# ─── 完整 cycle + SSE ────────────────────────────────────


@pytest.mark.asyncio
async def test_full_review_cycle_with_sse(client, fresh_db):
    """submit → SSE(reviewer) → reject → SSE(author) → 重提 → approve → active."""
    skill = _seed_draft(contributors=("u-author", "u-bob"))
    q_bob = await subscribe("u-bob")
    q_author = await subscribe("u-author")

    # 1. submit
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author"},
    )
    e_bob = await asyncio.wait_for(q_bob.get(), timeout=1.0)
    assert e_bob.event == "skill_review_request"
    assert e_bob.user_id == "u-bob"
    assert e_bob.extra and e_bob.extra.get("author_user_id") == "u-author"

    # 2. reject
    client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "u-bob", "reason": "more examples"},
    )
    e_author = await asyncio.wait_for(q_author.get(), timeout=1.0)
    assert e_author.event == "skill_review_rejected"
    assert "u-bob" in str(e_author.extra)

    # 3. 作者重提
    client.post(
        f"/skills/{skill.id}/submit-for-review",
        json={"user_id": "u-author", "note": "addressed"},
    )
    e_bob_2 = await asyncio.wait_for(q_bob.get(), timeout=1.0)
    assert e_bob_2.event == "skill_review_request"

    # 4. approve
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "u-bob"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    e_author_2 = await asyncio.wait_for(q_author.get(), timeout=1.0)
    assert e_author_2.event == "skill_review_approved"

    persisted = skill_service.get_skill(skill.id)
    assert persisted.status == "active"
    assert persisted.review_state == "approved"
    assert len(persisted.review_history) == 4  # submit/reject/submit/approve
