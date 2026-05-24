"""T66 · Members CRUD endpoints + ACL on review.

覆盖:
- /projects/:id/members: list / POST (bootstrap → first user becomes owner) / PATCH role / DELETE
- 401 缺 X-User-Id
- 403 非 owner 修改
- /me/memberships
- ACL on approve/reject:
  * X-User-Id 传 reviewer → ok
  * X-User-Id 不在 members → 403
  * body.reviewer_id ≠ X-User-Id → 403
  * Backward-compat: 无 header + 项目无 members → 不拦 (老行为)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.members import router as members_router
from app.gateway.http_api.skills import router as skills_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import Skill, SkillMetrics
from app.services import skill_service
from app.services.project import membership
from app.services.skill.consent import initialize_pending


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
    app.include_router(members_router)
    app.include_router(skills_router)
    return TestClient(app)


# ─── Members CRUD ────────────────────────────────────────


def test_post_members_requires_session(client):
    r = client.post(
        "/projects/p/members",
        json={"user_id": "ou-x", "role": "contributor"},
    )
    assert r.status_code == 401


def test_post_members_bootstrap_makes_first_caller_owner(client):
    r = client.post(
        "/projects/p/members",
        json={"user_id": "ignored", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["user_id"] == "ou-alice"
    assert body["role"] == "owner"  # bootstrap 强转 owner


def test_post_members_after_bootstrap_requires_owner(client):
    """有 member 后, 非 owner 不能 add."""
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )  # alice 成 owner
    # bob 不是 owner, 尝试 add 应 403
    r = client.post(
        "/projects/p/members",
        json={"user_id": "ou-carol", "role": "contributor"},
        headers={"X-User-Id": "ou-bob"},
    )
    assert r.status_code == 403


def test_post_members_owner_can_add_reviewer(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    r = client.post(
        "/projects/p/members",
        json={"user_id": "ou-bob", "role": "reviewer"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "reviewer"


def test_list_members(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    client.post(
        "/projects/p/members",
        json={"user_id": "ou-bob", "role": "reviewer"},
        headers={"X-User-Id": "ou-alice"},
    )
    client.post(
        "/projects/p/members",
        json={"user_id": "ou-carol", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    r = client.get("/projects/p/members")
    assert r.status_code == 200
    body = r.json()
    assert body["owner_count"] == 1
    assert body["reviewer_count"] == 1
    assert body["contributor_count"] == 1
    assert len(body["items"]) == 3


def test_patch_role_owner_only(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    client.post(
        "/projects/p/members",
        json={"user_id": "ou-bob", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    # alice (owner) 提升 bob
    r = client.patch(
        "/projects/p/members/ou-bob",
        json={"role": "reviewer"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "reviewer"
    # bob (非 owner) 提升 carol 应 403
    r2 = client.patch(
        "/projects/p/members/ou-carol",
        json={"role": "reviewer"},
        headers={"X-User-Id": "ou-bob"},
    )
    assert r2.status_code == 403


def test_patch_demote_last_owner_409(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    # alice 是唯一 owner, 试图自降为 reviewer
    r = client.patch(
        "/projects/p/members/ou-alice",
        json={"role": "reviewer"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 409


def test_delete_member_owner_only(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    client.post(
        "/projects/p/members",
        json={"user_id": "ou-bob", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    r = client.delete(
        "/projects/p/members/ou-bob",
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 204


def test_delete_last_owner_409(client):
    client.post(
        "/projects/p/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-alice"},
    )
    r = client.delete(
        "/projects/p/members/ou-alice",
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 409


def test_my_memberships_lists_cross_project(client):
    client.post(
        "/projects/p1/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-a"},
    )
    client.post(
        "/projects/p2/members",
        json={"user_id": "x", "role": "contributor"},
        headers={"X-User-Id": "ou-a"},
    )
    r = client.get("/me/memberships", headers={"X-User-Id": "ou-a"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    projects = {m["project_id"]: m["role"] for m in body["items"]}
    assert projects == {"p1": "owner", "p2": "owner"}


# ─── ACL on review endpoints ─────────────────────────────


def _seed_pending_review_skill(
    *, skill_id="s-r", project_id="proj-X",
) -> Skill:
    now = datetime.now(timezone.utc)
    skill = Skill(
        id=skill_id,
        project_id=project_id,
        name="needs-review",
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
        contributors=["ou-author"],
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        review_state="pending_review",
        review_history=[],
        last_reviewer_id=None,
        last_reviewed_at=None,
        created_at=now,
        updated_at=now,
    )
    skill_service.get_registry().add(skill)
    return skill


def test_approve_with_session_reviewer_ok(client, fresh_db):
    skill = _seed_pending_review_skill()
    # set up: alice=owner, bob=reviewer
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-X", user_id="ou-bob", role="reviewer",
        added_by="ou-alice",
    )
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-bob"},
        headers={"X-User-Id": "ou-bob"},
    )
    assert r.status_code == 200
    assert r.json()["review_state"] == "approved"


def test_approve_session_not_reviewer_403(client, fresh_db):
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-X", user_id="ou-carol", role="contributor",
        added_by="ou-alice",
    )
    # carol 仅 contributor, 尝试 approve
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-carol"},
        headers={"X-User-Id": "ou-carol"},
    )
    assert r.status_code == 403


def test_approve_body_mismatch_session_403(client, fresh_db):
    """body.reviewer_id 与 X-User-Id 不一致 → 拒 (防伪造)."""
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-X", user_id="ou-bob", role="reviewer",
        added_by="ou-alice",
    )
    # bob 自己是 reviewer, 但 body 谎称是 alice
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-alice"},
        headers={"X-User-Id": "ou-bob"},
    )
    assert r.status_code == 403
    assert "mismatch" in r.json()["detail"].lower()


def test_approve_backward_compat_no_header_no_members(client, fresh_db):
    """无 X-User-Id 且 project 无 members → 兼容 (老行为)."""
    skill = _seed_pending_review_skill()
    # 不 seed members
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-bob"},
    )
    # 应通过 (backward-compat); has_role 返 True
    assert r.status_code == 200


def test_approve_with_members_but_no_session_blocks(client, fresh_db):
    """项目有 members + 无 X-User-Id → backward-compat 退化用 body.reviewer_id 校验."""
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    # body.reviewer_id="ou-stranger" 不在 members → 拒
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-stranger"},
    )
    assert r.status_code == 403


def test_reject_with_session_reviewer_ok(client, fresh_db):
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-X", user_id="ou-bob", role="reviewer",
        added_by="ou-alice",
    )
    r = client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "ou-bob", "reason": "needs more examples"},
        headers={"X-User-Id": "ou-bob"},
    )
    assert r.status_code == 200
    assert r.json()["review_state"] == "rejected"


def test_reject_session_not_reviewer_403(client, fresh_db):
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    membership.add_member(
        project_id="proj-X", user_id="ou-carol", role="contributor",
        added_by="ou-alice",
    )
    r = client.post(
        f"/skills/{skill.id}/review/reject",
        json={"reviewer_id": "ou-carol", "reason": "no"},
        headers={"X-User-Id": "ou-carol"},
    )
    assert r.status_code == 403


def test_approve_owner_also_can_review(client, fresh_db):
    """owner 隐含 reviewer 权限."""
    skill = _seed_pending_review_skill()
    membership.add_member(
        project_id="proj-X", user_id="ou-alice", role="owner",
        added_by="ou-alice",
    )
    r = client.post(
        f"/skills/{skill.id}/review/approve",
        json={"reviewer_id": "ou-alice"},
        headers={"X-User-Id": "ou-alice"},
    )
    assert r.status_code == 200


# ─── T130.4 · PATCH /members/:user_id/im-binding ──────────────


def test_im_binding_self_can_bind(client: TestClient):
    """成员自己可绑定自己 (actor_id == user_id)."""
    # bootstrap owner
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "ou-owner", "role": "owner"},
    )
    # owner 添加 alice
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "alice@example.com", "role": "contributor"},
    )
    # alice 自助绑定
    resp = client.patch(
        "/projects/p1/members/alice@example.com/im-binding",
        headers={"X-User-Id": "alice@example.com"},
        json={"im_feishu_open_id": "ou_alice_open"},
    )
    assert resp.status_code == 200
    assert resp.json()["im_feishu_open_id"] == "ou_alice_open"


def test_im_binding_owner_can_bind_others(client: TestClient):
    """owner 可代成员绑定 (e.g. admin 帮员工初始化)."""
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "ou-owner", "role": "owner"},
    )
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "bob@example.com", "role": "contributor"},
    )
    resp = client.patch(
        "/projects/p1/members/bob@example.com/im-binding",
        headers={"X-User-Id": "ou-owner"},
        json={"im_feishu_open_id": "ou_bob_open"},
    )
    assert resp.status_code == 200
    assert resp.json()["im_feishu_open_id"] == "ou_bob_open"


def test_im_binding_other_member_forbidden(client: TestClient):
    """非 owner 不能改别人的 IM 绑定 → 403."""
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "ou-owner", "role": "owner"},
    )
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "alice@example.com", "role": "contributor"},
    )
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "carol@example.com", "role": "contributor"},
    )
    resp = client.patch(
        "/projects/p1/members/alice@example.com/im-binding",
        headers={"X-User-Id": "carol@example.com"},
        json={"im_feishu_open_id": "ou_hijack"},
    )
    assert resp.status_code == 403


def test_im_binding_clear_with_null(client: TestClient):
    """显式传 None 解绑."""
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "ou-owner", "role": "owner"},
    )
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "dave@example.com", "role": "contributor"},
    )
    # 先绑
    client.patch(
        "/projects/p1/members/dave@example.com/im-binding",
        headers={"X-User-Id": "dave@example.com"},
        json={"im_feishu_open_id": "ou_dave"},
    )
    # 解绑
    resp = client.patch(
        "/projects/p1/members/dave@example.com/im-binding",
        headers={"X-User-Id": "dave@example.com"},
        json={"im_feishu_open_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["im_feishu_open_id"] is None


def test_im_binding_member_not_found_404(client: TestClient):
    """非成员 → 404 (membership 服务抛 ProjectMembershipError)."""
    client.post(
        "/projects/p1/members",
        headers={"X-User-Id": "ou-owner"},
        json={"user_id": "ou-owner", "role": "owner"},
    )
    resp = client.patch(
        "/projects/p1/members/ghost@example.com/im-binding",
        headers={"X-User-Id": "ou-owner"},
        json={"im_feishu_open_id": "ou_x"},
    )
    assert resp.status_code == 404
