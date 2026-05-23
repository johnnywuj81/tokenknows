"""T68+T69 · Skill Marketplace (publish + browse + import)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.skills import router as skills_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import Skill, SkillMetrics
from app.services import skill_service
from app.services.project import membership
from app.services.skill import marketplace


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
    project_id="proj-A",
    name="demo",
    status="active",
    review_state="approved",
    visibility="private",
    trust=0.6,
    usage=10,
    locked=False,
) -> Skill:
    now = datetime.now(timezone.utc)
    return Skill(
        id=skill_id,
        project_id=project_id,
        name=name,
        version=1,
        skill_md=f"---\nname: {name}\n---\n# {name} body content example",
        embedding=None,
        metrics=SkillMetrics(
            usage_count=usage,
            acceptance_count=usage,
            rejection_count=0,
            avg_acceptance_rate=1.0 if usage > 0 else 0,
            trust_score=trust,
        ),
        distilled_from=[],
        distilled_at=now,
        last_used_at=now,
        locked=locked,
        status=status,
        parent_skill_id=None,
        contributors=[],
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state=review_state,
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        visibility=visibility,
        published_at=now if visibility == "public" else None,
        source_skill_id=None,
        source_project_id=None,
        imported_at=None,
        created_at=now,
        updated_at=now,
    )


# ─── publish_public ──────────────────────────────────────


def test_publish_active_approved_ok():
    s = _make_skill()
    out = marketplace.publish_public(s)
    assert out.visibility == "public"
    assert out.published_at is not None


def test_publish_already_public_idempotent():
    s = _make_skill(visibility="public")
    out = marketplace.publish_public(s)
    assert out is s


def test_publish_non_active_rejected():
    s = _make_skill(status="draft")
    with pytest.raises(marketplace.MarketplaceError) as exc:
        marketplace.publish_public(s)
    assert "active" in str(exc.value)


def test_publish_non_approved_rejected():
    s = _make_skill(review_state="not_submitted")
    with pytest.raises(marketplace.MarketplaceError):
        marketplace.publish_public(s)


def test_publish_locked_rejected():
    s = _make_skill(locked=True)
    with pytest.raises(marketplace.MarketplaceError):
        marketplace.publish_public(s)


def test_unpublish_idempotent_on_private():
    s = _make_skill(visibility="private")
    out = marketplace.unpublish(s)
    assert out is s


def test_unpublish_public_resets():
    s = _make_skill(visibility="public")
    out = marketplace.unpublish(s)
    assert out.visibility == "private"
    assert out.published_at is None


# ─── list_marketplace ────────────────────────────────────


def test_list_marketplace_only_returns_public(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="pub", visibility="public")
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="priv", visibility="private")
    )
    items = marketplace.list_marketplace()
    assert len(items) == 1
    assert items[0]["skill_id"] == "pub"


def test_list_marketplace_min_trust_filter(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="high", visibility="public", trust=0.8)
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="low", visibility="public", trust=0.2)
    )
    items = marketplace.list_marketplace(min_trust=0.5)
    ids = {it["skill_id"] for it in items}
    assert ids == {"high"}


def test_list_marketplace_query_filter(fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="pr-skill", name="pr-summary", visibility="public")
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="bg-skill", name="background", visibility="public")
    )
    items = marketplace.list_marketplace(q="summary")
    assert {it["skill_id"] for it in items} == {"pr-skill"}


def test_list_marketplace_sorted_by_published_at_desc(fresh_db):
    now = datetime.now(timezone.utc)
    older = _make_skill(skill_id="old", visibility="public")
    older = older.model_copy(update={
        "published_at": datetime(2026, 1, 1, tzinfo=timezone.utc)
    })
    newer = _make_skill(skill_id="new", visibility="public")
    newer = newer.model_copy(update={"published_at": now})
    skill_service.get_registry().add(older)
    skill_service.get_registry().add(newer)
    items = marketplace.list_marketplace()
    assert [it["skill_id"] for it in items] == ["new", "old"]


def test_list_marketplace_preview_truncated(fresh_db):
    long_md = "x" * 1000
    s = _make_skill(skill_id="long", visibility="public")
    s = s.model_copy(update={"skill_md": long_md})
    skill_service.get_registry().add(s)
    items = marketplace.list_marketplace()
    assert len(items[0]["skill_md_preview"]) == 500


# ─── import_skill ────────────────────────────────────────


def test_import_source_must_be_public():
    source = _make_skill(skill_id="src", visibility="private")
    with pytest.raises(marketplace.MarketplaceError):
        marketplace.import_skill(
            source_skill=source, target_project_id="proj-B"
        )


def test_import_creates_new_id_and_resets_metrics():
    source = _make_skill(
        skill_id="src", project_id="proj-A",
        visibility="public", trust=0.85, usage=50,
    )
    new_skill = marketplace.import_skill(
        source_skill=source, target_project_id="proj-B"
    )
    assert new_skill.id != source.id
    assert new_skill.project_id == "proj-B"
    assert new_skill.status == "draft"
    assert new_skill.review_state == "not_submitted"
    assert new_skill.visibility == "private"
    # metrics 重置
    assert new_skill.metrics.usage_count == 0
    assert new_skill.metrics.acceptance_count == 0
    assert new_skill.metrics.trust_score == 0.5
    # 来源追溯
    assert new_skill.source_skill_id == "src"
    assert new_skill.source_project_id == "proj-A"
    assert new_skill.imported_at is not None


def test_import_with_name_hint_overrides():
    source = _make_skill(skill_id="src", name="orig-name", visibility="public")
    new_skill = marketplace.import_skill(
        source_skill=source,
        target_project_id="proj-B",
        name_hint="custom-name",
    )
    assert new_skill.name == "custom-name"


def test_import_clears_consent_fields():
    """import 不应继承上游 consent (新 project 独立)."""
    source = _make_skill(skill_id="src", visibility="public")
    source = source.model_copy(update={
        "contributors": ["ou-a"],
        "consent_required_from": ["ou-a"],
    })
    new_skill = marketplace.import_skill(
        source_skill=source, target_project_id="proj-B"
    )
    assert new_skill.contributors == []
    assert new_skill.consent_required_from == []


def test_import_breaks_evolve_chain():
    """跨 project import 不继续 evolve_chain (parent_skill_id=None)."""
    source = _make_skill(skill_id="src", visibility="public")
    source = source.model_copy(update={
        "version": 5, "parent_skill_id": "src-v4"
    })
    new_skill = marketplace.import_skill(
        source_skill=source, target_project_id="proj-B"
    )
    assert new_skill.version == 1  # 重新计版本
    assert new_skill.parent_skill_id is None


# ─── HTTP endpoints ──────────────────────────────────────


def test_publish_endpoint_owner_only(client, fresh_db):
    skill_service.get_registry().add(_make_skill(skill_id="s-1"))
    membership.add_member(
        project_id="proj-A", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-A", user_id="ou-bob", role="reviewer",
        added_by="ou-alice",
    )
    # bob (reviewer) 试图 publish → 403
    r = client.post(
        "/skills/s-1/publish", headers={"X-User-Id": "ou-bob"}
    )
    assert r.status_code == 403
    # alice (owner) ok
    r = client.post(
        "/skills/s-1/publish", headers={"X-User-Id": "ou-alice"}
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "public"


def test_publish_endpoint_404(client, fresh_db):
    membership.add_member(
        project_id="proj-A", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/skills/s-nope/publish", headers={"X-User-Id": "ou-alice"}
    )
    assert r.status_code == 404


def test_publish_endpoint_409_status_not_active(client, fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="s-draft", status="draft")
    )
    membership.add_member(
        project_id="proj-A", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/skills/s-draft/publish", headers={"X-User-Id": "ou-alice"}
    )
    assert r.status_code == 409


def test_unpublish_endpoint_owner_only(client, fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="s-1", visibility="public")
    )
    membership.add_member(
        project_id="proj-A", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/skills/s-1/unpublish", headers={"X-User-Id": "ou-alice"}
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "private"


def test_marketplace_list_endpoint(client, fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="pub", visibility="public")
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="priv", visibility="private")
    )
    r = client.get("/marketplace/skills")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["skill_id"] == "pub"


def test_marketplace_list_query_param(client, fresh_db):
    skill_service.get_registry().add(
        _make_skill(skill_id="pr", name="pr-summary", visibility="public")
    )
    skill_service.get_registry().add(
        _make_skill(skill_id="bg", name="background", visibility="public")
    )
    r = client.get("/marketplace/skills?q=summary")
    assert r.status_code == 200
    assert {it["skill_id"] for it in r.json()["items"]} == {"pr"}


def test_import_endpoint_requires_contributor(client, fresh_db):
    src = _make_skill(skill_id="src", project_id="proj-A", visibility="public")
    skill_service.get_registry().add(src)
    membership.add_member(
        project_id="proj-B", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    # stranger 试图 import → 403
    r = client.post(
        "/projects/proj-B/skills/import",
        json={"source_skill_id": "src"},
        headers={"X-User-Id": "ou-stranger"},
    )
    assert r.status_code == 403


def test_import_endpoint_404_source(client, fresh_db):
    membership.add_member(
        project_id="proj-B", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/projects/proj-B/skills/import",
        json={"source_skill_id": "src-nope"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 404


def test_import_endpoint_409_source_private(client, fresh_db):
    skill_service.get_registry().add(
        _make_skill(
            skill_id="src", project_id="proj-A", visibility="private",
        )
    )
    membership.add_member(
        project_id="proj-B", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/projects/proj-B/skills/import",
        json={"source_skill_id": "src"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 409


def test_import_endpoint_happy(client, fresh_db):
    src = _make_skill(
        skill_id="src", project_id="proj-A", name="awesome-skill",
        visibility="public",
    )
    skill_service.get_registry().add(src)
    membership.add_member(
        project_id="proj-B", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        "/projects/proj-B/skills/import",
        json={"source_skill_id": "src", "name_hint": "renamed"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["project_id"] == "proj-B"
    assert body["name"] == "renamed"
    assert body["source_skill_id"] == "src"
    assert body["source_project_id"] == "proj-A"
    assert body["status"] == "draft"
    assert body["review_state"] == "not_submitted"
    assert body["visibility"] == "private"
