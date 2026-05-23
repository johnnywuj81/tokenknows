"""T62 · Skill governance summary + evolve-chain endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.skills import router as skills_router
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


@pytest.fixture
def client(fresh_db) -> TestClient:
    app = FastAPI()
    app.include_router(skills_router)
    return TestClient(app)


def _make_skill(
    *,
    skill_id="s-1",
    project_id="proj-X",
    status="active",
    review_state="approved",
    trust=0.5,
    usage=10,
    acc=5,
    rej=5,
    last_used_at: datetime | None = None,
    version=1,
    parent_id: str | None = None,
    locked=False,
) -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id=skill_id,
        project_id=project_id,
        name=f"name-{skill_id}",
        version=version,
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
        parent_skill_id=parent_id,
        contributors=[],
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state=review_state,
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


# ─── build_governance_summary ────────────────────────────


def test_governance_empty_project(fresh_db):
    summary = skill_pool.build_governance_summary("proj-empty")
    assert summary["total"] == 0
    assert summary["by_status"] == {}
    assert summary["avg_trust_score"] == 0.0


def test_governance_counts_by_status_and_review(fresh_db):
    skill_service.get_registry().add(_make_skill(
        skill_id="s-1", status="active", review_state="approved",
        last_used_at=datetime.now(timezone.utc), trust=0.7,
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-2", status="draft", review_state="pending_review",
        last_used_at=datetime.now(timezone.utc), trust=0.6,
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-3", status="deprecated", review_state="approved",
        trust=0.1,
    ))
    summary = skill_pool.build_governance_summary("proj-X")
    assert summary["total"] == 3
    assert summary["by_status"]["active"] == 1
    assert summary["by_status"]["draft"] == 1
    assert summary["by_status"]["deprecated"] == 1
    assert summary["by_review_state"]["approved"] == 2
    assert summary["by_review_state"]["pending_review"] == 1
    # avg_trust 只算 active: 0.7
    assert summary["avg_trust_score"] == 0.7


def test_governance_candidate_counts(fresh_db):
    """evolve / dormant / low_trust 候选都被计入."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    # evolve 候选: usage=25, acc=4
    skill_service.get_registry().add(_make_skill(
        skill_id="s-bad", usage=25, acc=4, rej=21,
        last_used_at=datetime.now(timezone.utc),
        trust=0.3,
    ))
    # dormant 候选
    skill_service.get_registry().add(_make_skill(
        skill_id="s-dorm", trust=0.5, last_used_at=long_ago,
    ))
    # low_trust 候选
    skill_service.get_registry().add(_make_skill(
        skill_id="s-low",
        trust=0.15, last_used_at=datetime.now(timezone.utc),
    ))
    summary = skill_pool.build_governance_summary("proj-X")
    assert summary["evolve_candidates"] == 1
    assert summary["dormant_candidates"] == 1
    assert summary["low_trust_candidates"] == 1


def test_governance_filters_by_project(fresh_db):
    skill_service.get_registry().add(_make_skill(skill_id="s-x", project_id="proj-X"))
    skill_service.get_registry().add(_make_skill(skill_id="s-y", project_id="proj-Y"))
    summary_x = skill_pool.build_governance_summary("proj-X")
    summary_y = skill_pool.build_governance_summary("proj-Y")
    assert summary_x["total"] == 1
    assert summary_y["total"] == 1


# ─── build_evolve_chain ──────────────────────────────────


def test_evolve_chain_single_skill_no_parent_no_children(fresh_db):
    skill_service.get_registry().add(_make_skill(skill_id="s-solo"))
    chain = skill_pool.build_evolve_chain("s-solo")
    assert len(chain) == 1
    assert chain[0]["skill_id"] == "s-solo"
    assert chain[0]["is_current"] is True


def test_evolve_chain_with_parent_children(fresh_db):
    """v1 → v2 (current) → v3 链."""
    skill_service.get_registry().add(_make_skill(
        skill_id="s-v1", version=1, status="deprecated",
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-v2", version=2, status="deprecated", parent_id="s-v1",
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-v3", version=3, parent_id="s-v2",
    ))
    chain = skill_pool.build_evolve_chain("s-v2")
    assert [n["skill_id"] for n in chain] == ["s-v1", "s-v2", "s-v3"]
    # is_current 标记
    currents = [n for n in chain if n["is_current"]]
    assert len(currents) == 1
    assert currents[0]["skill_id"] == "s-v2"


def test_evolve_chain_branching_picks_all_descendants(fresh_db):
    """current 有 2 children (e.g. 不同 evolve cycle)."""
    skill_service.get_registry().add(_make_skill(skill_id="s-root", version=1))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-c1", version=2, parent_id="s-root"
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-c2", version=2, parent_id="s-root"
    ))
    chain = skill_pool.build_evolve_chain("s-root")
    ids = [n["skill_id"] for n in chain]
    assert ids[0] == "s-root"
    assert set(ids[1:]) == {"s-c1", "s-c2"}


def test_evolve_chain_missing_skill_returns_empty(fresh_db):
    assert skill_pool.build_evolve_chain("s-nope") == []


# ─── endpoints ───────────────────────────────────────────


def test_get_governance_summary_endpoint(client, fresh_db):
    skill_service.get_registry().add(_make_skill(
        skill_id="s-1", project_id="proj-X",
        last_used_at=datetime.now(timezone.utc), trust=0.6,
    ))
    r = client.get("/projects/proj-X/skills/governance")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == "proj-X"
    assert body["total"] == 1
    assert body["by_status"]["active"] == 1


def test_get_evolve_chain_endpoint(client, fresh_db):
    skill_service.get_registry().add(_make_skill(skill_id="s-v1", version=1))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-v2", version=2, parent_id="s-v1",
    ))
    r = client.get("/skills/s-v2/evolve-chain")
    assert r.status_code == 200
    body = r.json()
    assert body["skill_id"] == "s-v2"
    assert len(body["nodes"]) == 2
    assert body["nodes"][0]["skill_id"] == "s-v1"


def test_get_evolve_chain_404_missing(client):
    r = client.get("/skills/s-nope/evolve-chain")
    assert r.status_code == 404


def test_trigger_trust_recompute_endpoint(client, fresh_db):
    skill_service.get_registry().add(_make_skill(
        skill_id="s-1", project_id="proj-X",
        last_used_at=datetime.now(timezone.utc), trust=0.5,
    ))
    r = client.post(
        "/projects/proj-X/skills/governance/run-trust-recompute"
    )
    assert r.status_code == 200
    body = r.json()
    assert "scanned" in body
    assert "updated" in body


def test_trigger_deprecation_sweep_endpoint(client, fresh_db):
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    skill_service.get_registry().add(_make_skill(
        skill_id="s-old", project_id="proj-X", last_used_at=long_ago,
    ))
    r = client.post(
        "/projects/proj-X/skills/governance/run-deprecation-sweep"
    )
    assert r.status_code == 200
    body = r.json()
    assert "remaining_candidates" in body
    # 跑完后该 skill 应已转 deprecated, 候选清空
    assert body["remaining_candidates"] == 0
