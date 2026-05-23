"""T53 · consent 流程 SSE 集成.

验证 notify_all / notify_followup / sign / reject 真在 SSE 队列里推送事件,
而不只是写 web notification.
"""

from __future__ import annotations

import asyncio
import json
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
from app.services.im import consent_notifier
from app.services.notification_sse import (
    queues_for_user,
    reset_for_tests,
    subscribe,
)
from app.services.skill.consent import initialize_pending


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


def _make_pending(contribs=("ou-a", "ou-b")) -> Skill:
    now = datetime.now(timezone.utc)
    skill = Skill(
        id="skill-sse-1",
        project_id="proj-X",
        name="im-distilled-sse",
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
        contributors=list(contribs),
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    return initialize_pending(skill)


# ─── notify_all → SSE ───────────────────────────────────


@pytest.mark.asyncio
async def test_notify_all_publishes_sse_to_each_contributor(fresh_db):
    qa = await subscribe("ou-a")
    qb = await subscribe("ou-b")
    skill = _make_pending(("ou-a", "ou-b"))
    consent_notifier.notify_all(skill, connection_raw=None)

    # 各收到 1 个 consent_request
    ea = await asyncio.wait_for(qa.get(), timeout=1.0)
    eb = await asyncio.wait_for(qb.get(), timeout=1.0)
    assert ea.event == "consent_request"
    assert ea.user_id == "ou-a"
    assert ea.skill_id == "skill-sse-1"
    assert ea.unread_count == 1
    assert eb.event == "consent_request"
    assert eb.user_id == "ou-b"


@pytest.mark.asyncio
async def test_notify_all_skips_sse_when_no_subscriber(fresh_db):
    """无订阅 → publish 返 0, 但 web notification 仍写."""
    skill = _make_pending(("ou-a",))
    report = consent_notifier.notify_all(skill, connection_raw=None)
    assert report.web_success == 1
    # ou-a 没订阅, 不抛
    assert queues_for_user("ou-a") == 0


@pytest.mark.asyncio
async def test_notify_all_isolation_between_users(fresh_db):
    """ou-a 订阅不应收到 ou-b 的事件."""
    qa = await subscribe("ou-a")
    qb = await subscribe("ou-b")
    # 只对 ou-a 发
    skill = _make_pending(("ou-a",))
    consent_notifier.notify_all(skill, connection_raw=None)
    await asyncio.wait_for(qa.get(), timeout=1.0)
    assert qb.qsize() == 0


# ─── sign endpoint → SSE followup ────────────────────────


@pytest.mark.asyncio
async def test_sign_endpoint_publishes_consent_signed_to_others(
    client, fresh_db
):
    skill = _make_pending(("ou-a", "ou-b", "ou-c"))
    skill_service.get_registry().add(skill)
    # ou-b / ou-c 订阅
    qb = await subscribe("ou-b")
    qc = await subscribe("ou-c")
    qa = await subscribe("ou-a")
    # 主路径
    r = client.post(
        f"/skills/{skill.id}/consent/sign",
        json={"user_id": "ou-a", "channel": "web"},
    )
    assert r.status_code == 200
    # ou-b / ou-c 应该收 consent_signed
    eb = await asyncio.wait_for(qb.get(), timeout=1.0)
    assert eb.event == "consent_signed"
    assert eb.skill_id == skill.id
    assert eb.extra and eb.extra.get("actor_user_id") == "ou-a"
    ec = await asyncio.wait_for(qc.get(), timeout=1.0)
    assert ec.event == "consent_signed"
    # ou-a 不收 (自己)
    assert qa.qsize() == 0


@pytest.mark.asyncio
async def test_reject_endpoint_publishes_consent_rejected_to_others(
    client, fresh_db
):
    skill = _make_pending(("ou-a", "ou-b"))
    skill_service.get_registry().add(skill)
    qb = await subscribe("ou-b")
    qa = await subscribe("ou-a")
    r = client.post(
        f"/skills/{skill.id}/consent/reject",
        json={"user_id": "ou-a", "channel": "web", "reason": "HR 私下"},
    )
    assert r.status_code == 200
    eb = await asyncio.wait_for(qb.get(), timeout=1.0)
    assert eb.event == "consent_rejected"
    assert qa.qsize() == 0  # actor 不收
