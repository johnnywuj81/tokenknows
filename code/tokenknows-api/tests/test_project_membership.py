"""T65 · ProjectMember schema + storage + ACL.

覆盖:
- schema 校验 (role Literal / id 必填)
- add_member / update_role / remove_member CRUD
- 拒绝删/降级最后一个 owner
- has_role / is_owner / can_review / can_contribute
- Backward-compat: 无 members 时默认 True (除 strict)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.project_member import ProjectMember
from app.services.project import membership


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


# ─── Schema ───────────────────────────────────────────────


def test_role_literal_valid():
    m = ProjectMember(
        id="member-1",
        project_id="p",
        user_id="u",
        role="owner",
        added_by="u",
        added_at=datetime.now(timezone.utc),
    )
    assert m.role == "owner"


def test_role_literal_invalid():
    with pytest.raises(ValidationError):
        ProjectMember(
            id="member-1",
            project_id="p",
            user_id="u",
            role="superuser",  # type: ignore[arg-type]
            added_by="u",
            added_at=datetime.now(timezone.utc),
        )


# ─── CRUD ────────────────────────────────────────────────


def test_add_member_persists(fresh_db):
    m = membership.add_member(
        project_id="p-1",
        user_id="ou-alice",
        role="contributor",
        added_by="ou-bob",
    )
    assert m.role == "contributor"
    persisted = membership.get_member("p-1", "ou-alice")
    assert persisted is not None
    assert persisted.role == "contributor"


def test_add_member_upserts_role(fresh_db):
    """同 (project, user) 第二次 add 应更新 role."""
    membership.add_member(
        project_id="p-1", user_id="ou-a", role="contributor", added_by="ou-b",
    )
    membership.add_member(
        project_id="p-1", user_id="ou-a", role="reviewer", added_by="ou-b",
    )
    persisted = membership.get_member("p-1", "ou-a")
    assert persisted.role == "reviewer"


def test_list_members_filtering(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-owner", role="owner", added_by="ou-owner",
    )
    membership.add_member(
        project_id="p", user_id="ou-r1", role="reviewer", added_by="ou-owner",
    )
    membership.add_member(
        project_id="p", user_id="ou-r2", role="reviewer", added_by="ou-owner",
    )
    membership.add_member(
        project_id="p", user_id="ou-c1", role="contributor", added_by="ou-owner",
    )
    assert len(membership.list_members("p")) == 4
    assert len(membership.list_members("p", role="reviewer")) == 2
    assert len(membership.list_members("p", role="owner")) == 1


def test_remove_member(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-c", role="contributor", added_by="ou-owner",
    )
    assert membership.remove_member("p", "ou-c") is True
    assert membership.get_member("p", "ou-c") is None
    # 再删返 False
    assert membership.remove_member("p", "ou-c") is False


def test_remove_last_owner_rejected(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-owner", role="owner", added_by="ou-owner",
    )
    with pytest.raises(membership.ProjectMembershipError) as exc_info:
        membership.remove_member("p", "ou-owner")
    assert "last owner" in str(exc_info.value)


def test_remove_owner_when_multiple_ok(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-a", role="owner", added_by="ou-a",
    )
    membership.add_member(
        project_id="p", user_id="ou-b", role="owner", added_by="ou-a",
    )
    assert membership.remove_member("p", "ou-a") is True
    # 留 1 owner, 不能再删
    with pytest.raises(membership.ProjectMembershipError):
        membership.remove_member("p", "ou-b")


def test_update_role_demote_last_owner_rejected(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-only", role="owner", added_by="ou-only",
    )
    with pytest.raises(membership.ProjectMembershipError):
        membership.update_role(
            project_id="p", user_id="ou-only", new_role="reviewer",
            actor_id="ou-only",
        )


def test_update_role_promote_ok(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-owner", role="owner", added_by="ou-owner",
    )
    membership.add_member(
        project_id="p", user_id="ou-c", role="contributor", added_by="ou-owner",
    )
    membership.update_role(
        project_id="p", user_id="ou-c", new_role="reviewer",
        actor_id="ou-owner",
    )
    assert membership.get_member("p", "ou-c").role == "reviewer"


def test_update_role_missing_member_raises(fresh_db):
    with pytest.raises(membership.ProjectMembershipError):
        membership.update_role(
            project_id="p", user_id="ou-nope", new_role="reviewer",
            actor_id="ou-x",
        )


# ─── ACL ─────────────────────────────────────────────────


def test_has_role_owner_implies_reviewer_and_contributor(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-o", role="owner", added_by="ou-o",
    )
    assert membership.has_role(
        user_id="ou-o", project_id="p", required="owner"
    )
    assert membership.has_role(
        user_id="ou-o", project_id="p", required="reviewer"
    )
    assert membership.has_role(
        user_id="ou-o", project_id="p", required="contributor"
    )


def test_has_role_reviewer_blocks_owner(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-o", role="owner", added_by="ou-o",
    )
    membership.add_member(
        project_id="p", user_id="ou-r", role="reviewer", added_by="ou-o",
    )
    assert not membership.is_owner("ou-r", "p")
    assert membership.can_review("ou-r", "p")
    assert membership.can_contribute("ou-r", "p")


def test_has_role_contributor_only(fresh_db):
    membership.add_member(
        project_id="p", user_id="ou-o", role="owner", added_by="ou-o",
    )
    membership.add_member(
        project_id="p", user_id="ou-c", role="contributor", added_by="ou-o",
    )
    assert membership.can_contribute("ou-c", "p")
    assert not membership.can_review("ou-c", "p", strict=True)
    assert not membership.is_owner("ou-c", "p")


def test_has_role_unknown_user_strict(fresh_db):
    """strict=True + 无成员记录 → 拒绝."""
    membership.add_member(
        project_id="p", user_id="ou-o", role="owner", added_by="ou-o",
    )
    assert not membership.has_role(
        user_id="ou-stranger", project_id="p", required="contributor",
        strict=True,
    )


def test_has_role_backward_compat_no_members_ok(fresh_db):
    """空 project (无任何成员) + non-strict → 默认 True (兼容)."""
    assert membership.has_role(
        user_id="ou-anything", project_id="p-empty", required="reviewer"
    )
    assert membership.has_role(
        user_id="ou-anything", project_id="p-empty", required="owner"
    )


def test_has_role_with_members_unknown_user_blocked(fresh_db):
    """有 1 个 member 后, 不在列表的 user 拒 (即便 non-strict)."""
    membership.add_member(
        project_id="p", user_id="ou-o", role="owner", added_by="ou-o",
    )
    assert not membership.has_role(
        user_id="ou-stranger", project_id="p", required="contributor"
    )


def test_list_user_project_memberships(fresh_db):
    """跨 project: ou-a 在 p1 是 owner, 在 p2 是 contributor."""
    membership.add_member(
        project_id="p1", user_id="ou-a", role="owner", added_by="ou-a",
    )
    membership.add_member(
        project_id="p2", user_id="ou-a", role="contributor", added_by="ou-x",
    )
    rows = fresh_db.list_user_project_memberships("ou-a")
    assert len(rows) == 2
    projects = {r["project_id"]: r["role"] for r in rows}
    assert projects == {"p1": "owner", "p2": "contributor"}
