"""skills HTTP endpoints (v0.2).

覆盖 8 个 endpoint:
- GET    /projects/:id/skills
- GET    /skills/:id
- POST   /projects/:id/skills/distill
- PATCH  /skills/:id
- POST   /skills/:id/lock + /unlock
- POST   /skills/:id/evolve
- DELETE /skills/:id
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset, Chapter
from app.schemas.skill import Skill, SkillMetrics
from app.services import generation_service, skill_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    skill_service.reset_registry_for_tests()
    generation_service._assets.clear()
    generation_service._chapters.clear()
    yield new_store


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_skill(skill_id: str = "skill-1", project_id: str = "p1", **overrides) -> Skill:
    defaults = dict(
        id=skill_id,
        project_id=project_id,
        name="formatter",
        version=1,
        skill_md="---\nname: formatter\n---\n# body",
        embedding=[1.0, 0.0],
        metrics=SkillMetrics(
            usage_count=10, acceptance_count=8, rejection_count=2,
            avg_acceptance_rate=0.8, trust_score=0.75,
        ),
        distilled_at=_now(),
        status="active",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    skill = Skill(**defaults)
    skill_service.get_registry().add(skill)
    return skill


def _seed_asset_and_chapter(
    asset_id: str = "a1", chapter_id: str = "ch-1",
    project_id: str = "p1", applied_skills=None,
    approval_state: str = "pending",
) -> tuple[Asset, Chapter]:
    asset = Asset(
        id=asset_id, project_id=project_id, type="weekly_report", title="t",
        status="draft", current_version=1, template_id=None, created_by="u",
        created_at=_now(), updated_at=_now(),
    )
    chapter = Chapter(
        id=chapter_id, asset_id=asset_id, asset_version=1, order_index=0,
        title="测试", content="文本内容 " * 50,
        applied_skills=applied_skills or [],
        approval_state=approval_state,  # type: ignore[arg-type]
    )
    generation_service._assets[asset_id] = asset
    generation_service._chapters[asset_id] = [chapter]
    return asset, chapter


# ─── GET list ────────────────────────────────────────────────


def test_list_skills_empty_returns_empty_array(client: TestClient) -> None:
    r = client.get("/api/v1/projects/empty-proj/skills")
    assert r.status_code == 200
    assert r.json() == []


def test_list_skills_filter_by_status(client: TestClient) -> None:
    _seed_skill("s1", status="draft", trust_score=0.5)
    _seed_skill("s2", status="active", trust_score=0.5)
    r = client.get("/api/v1/projects/p1/skills?status=active")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert ids == ["s2"]


def test_list_skills_sorted_by_trust(client: TestClient) -> None:
    _seed_skill("s-low", trust_score=0.2)
    _seed_skill("s-high", trust_score=0.9)
    r = client.get("/api/v1/projects/p1/skills")
    ids = [s["id"] for s in r.json()]
    assert ids[0] == "s-high"


# ─── GET detail ──────────────────────────────────────────────


def test_get_skill_returns_full_dump(client: TestClient) -> None:
    skill = _seed_skill("s1")
    r = client.get(f"/api/v1/skills/{skill.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "s1"
    assert data["skill_md"].startswith("---")


def test_get_skill_404_when_missing(client: TestClient) -> None:
    r = client.get("/api/v1/skills/ghost")
    assert r.status_code == 404


# ─── POST distill ───────────────────────────────────────────


def test_distill_skill_happy_path(client: TestClient) -> None:
    _seed_asset_and_chapter("a1", "ch-1", project_id="p1")

    mock_response = type("MockResp", (), {
        "text": "---\nname: new-skill\n---\n# body",
        "provider": "anthropic",
        "model_used": "claude",
        "usage": {},
        "fallback_used": False,
    })()
    with patch(
        "app.services.skill_service.get_router",
        new=AsyncMock(return_value=type("R", (), {"generate": AsyncMock(return_value=mock_response)})()),
    ), patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[0.1, 0.2]]),
    ):
        r = client.post(
            "/api/v1/projects/p1/skills/distill",
            json={"source_chapter_ids": ["ch-1"]},
        )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "new-skill"
    assert data["status"] == "draft"
    assert data["project_id"] == "p1"


def test_distill_skill_404_when_no_chapter_matches(client: TestClient) -> None:
    r = client.post(
        "/api/v1/projects/p1/skills/distill",
        json={"source_chapter_ids": ["nonexistent"]},
    )
    assert r.status_code == 404


def test_distill_skill_rejects_empty_sources(client: TestClient) -> None:
    """Pydantic min_length=1 应在 422 阻止."""
    r = client.post(
        "/api/v1/projects/p1/skills/distill",
        json={"source_chapter_ids": []},
    )
    assert r.status_code == 422


# ─── PATCH ──────────────────────────────────────────────────


def test_update_skill_locked_flag(client: TestClient) -> None:
    _seed_skill("s1")
    r = client.patch("/api/v1/skills/s1", json={"locked": True})
    assert r.status_code == 200
    assert r.json()["locked"] is True


def test_update_skill_404_when_missing(client: TestClient) -> None:
    r = client.patch("/api/v1/skills/ghost", json={"locked": True})
    assert r.status_code == 404


# ─── lock / unlock ──────────────────────────────────────────


def test_lock_unlock_cycle(client: TestClient) -> None:
    _seed_skill("s1")
    r1 = client.post("/api/v1/skills/s1/lock")
    assert r1.status_code == 200
    assert r1.json()["locked"] is True
    r2 = client.post("/api/v1/skills/s1/unlock")
    assert r2.status_code == 200
    assert r2.json()["locked"] is False


def test_lock_404_when_missing(client: TestClient) -> None:
    r = client.post("/api/v1/skills/ghost/lock")
    assert r.status_code == 404


# ─── evolve ─────────────────────────────────────────────────


def test_evolve_404_when_skill_missing(client: TestClient) -> None:
    r = client.post("/api/v1/skills/ghost/evolve")
    assert r.status_code == 404


def test_evolve_409_when_locked(client: TestClient) -> None:
    _seed_skill("s1", locked=True)
    r = client.post("/api/v1/skills/s1/evolve")
    assert r.status_code == 409


def test_evolve_409_when_no_failing_chapters(client: TestClient) -> None:
    _seed_skill("s1")
    r = client.post("/api/v1/skills/s1/evolve")
    assert r.status_code == 409


def test_evolve_happy_path(client: TestClient) -> None:
    _seed_skill("s1")
    # seed 一个 rejected chapter 应用过此 skill
    _seed_asset_and_chapter(
        "a1", "ch-1", project_id="p1",
        approval_state="rejected",
        applied_skills=[{"skill_id": "s1", "version": 1, "applied_at": _now().isoformat()}],
    )
    mock_response = type("MockResp", (), {
        "text": "---\nname: formatter-v2\n---\n# improved",
        "provider": "anthropic",
        "model_used": "claude",
        "usage": {},
        "fallback_used": False,
    })()
    with patch(
        "app.services.skill_service.get_router",
        new=AsyncMock(return_value=type("R", (), {"generate": AsyncMock(return_value=mock_response)})()),
    ), patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[0.5, 0.5]]),
    ):
        r = client.post("/api/v1/skills/s1/evolve")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 2
    assert data["parent_skill_id"] == "s1"


# ─── DELETE ─────────────────────────────────────────────────


def test_delete_skill(client: TestClient) -> None:
    _seed_skill("s1")
    r = client.delete("/api/v1/skills/s1")
    assert r.status_code == 204
    assert skill_service.get_skill("s1") is None


def test_delete_skill_404(client: TestClient) -> None:
    r = client.delete("/api/v1/skills/ghost")
    assert r.status_code == 404
