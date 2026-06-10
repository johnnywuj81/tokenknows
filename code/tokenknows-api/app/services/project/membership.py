"""ProjectMember CRUD + ACL service · v0.9.0 T65.

替换 trust-on-faith user_id: 端点用 has_role(user_id, project_id, required)
强制校验.

ACL 隐含规则:
- owner ⊇ reviewer ⊇ contributor (owner 隐含拥有低权)
- 检查时用 _ROLE_RANK: 用户实际 role 数值 >= 要求 → 通过

Backward-compat:
- 项目无 members 时, has_role 默认 True (兼容 v0.5/v0.6 不强制 ACL 的旧代码)
- 等所有 endpoint 都启用 ACL + 至少 1 个 owner 后, 切到 strict mode (留 v0.10)
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from app.config.logging import logger
from app.persistence import store as store_module
from app.schemas.project_member import ProjectMember, ProjectMemberRole

# v1.0.1 (review fix): bootstrap 防竞态 - 进程内锁
# 多进程不够 (需 DB 级 unique constraint), v1.1 上 JWT + 真实 user 后再加.
_bootstrap_lock = threading.Lock()


# role 数值排序: 高 → 低权; 用户实际 role 数值 >= 要求 role → has_role=True
_ROLE_RANK: dict[ProjectMemberRole, int] = {
    "owner": 3,
    "reviewer": 2,
    "contributor": 1,
}


class ProjectMembershipError(Exception):
    """成员管理操作非法 (e.g. 不能删最后一个 owner)."""


# ─── CRUD ────────────────────────────────────────────────


def add_member(
    *,
    project_id: str,
    user_id: str,
    role: ProjectMemberRole,
    added_by: str,
    note: str | None = None,
    now: datetime | None = None,
) -> ProjectMember:
    """添加 / 更新成员 (project_id, user_id) UNIQUE 约束自动 upsert role."""
    db = store_module.get_db()
    now_utc = now or datetime.now(UTC)
    member = ProjectMember(
        id=f"member-{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        user_id=user_id,
        role=role,
        added_by=added_by,
        added_at=now_utc,
        note=note,
    )
    db.upsert_project_member(
        member_id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        added_by=member.added_by,
        added_at=member.added_at.isoformat(),
        json_str=member.model_dump_json(),
    )
    logger.info(
        "project_member_added",
        project_id=project_id, user_id=user_id, role=role,
    )
    return member


def remove_member(project_id: str, user_id: str) -> bool:
    """移除成员. 拒绝删最后一个 owner (项目无主)."""
    db = store_module.get_db()
    existing = db.get_project_member(project_id, user_id)
    if existing and existing.get("role") == "owner":
        owners = db.list_project_members(project_id, role="owner")
        if len(owners) <= 1:
            raise ProjectMembershipError(
                f"cannot remove last owner of project {project_id}"
            )
    return db.remove_project_member(project_id, user_id)


def update_role(
    *,
    project_id: str,
    user_id: str,
    new_role: ProjectMemberRole,
    actor_id: str,
    now: datetime | None = None,
) -> ProjectMember:
    """改 role; 同样拒绝把最后一个 owner 降级."""
    db = store_module.get_db()
    existing = db.get_project_member(project_id, user_id)
    if existing is None:
        raise ProjectMembershipError(
            f"member not found: project={project_id} user={user_id}"
        )
    if existing.get("role") == "owner" and new_role != "owner":
        owners = db.list_project_members(project_id, role="owner")
        if len(owners) <= 1:
            raise ProjectMembershipError(
                f"cannot demote last owner of project {project_id}"
            )
    return add_member(
        project_id=project_id,
        user_id=user_id,
        role=new_role,
        added_by=actor_id,
        note=existing.get("note"),
        now=now,
    )


def list_members(
    project_id: str, role: ProjectMemberRole | None = None
) -> list[ProjectMember]:
    db = store_module.get_db()
    rows = db.list_project_members(project_id, role=role)
    return [ProjectMember.model_validate(r) for r in rows]


def get_member(
    project_id: str, user_id: str
) -> ProjectMember | None:
    db = store_module.get_db()
    raw = db.get_project_member(project_id, user_id)
    if raw is None:
        return None
    return ProjectMember.model_validate(raw)


def update_im_binding(
    *,
    project_id: str,
    user_id: str,
    im_feishu_open_id: str | None,
) -> ProjectMember:
    """T130.4 · 自助绑定/解绑飞书 open_id.

    空字符串 / None → 解绑. 非空时建议但不强制 'ou_' 前缀 (留给前端校验,
    后端容忍格式以备其它 IM 平台未来扩展).

    Raises ProjectMembershipError if member not found.
    """
    existing = get_member(project_id, user_id)
    if existing is None:
        raise ProjectMembershipError(
            f"member not found: project={project_id} user={user_id}"
        )
    # 空字符串视为解绑
    normalized = (im_feishu_open_id or "").strip() or None
    updated = existing.model_copy(update={"im_feishu_open_id": normalized})
    db = store_module.get_db()
    db.upsert_project_member(
        member_id=updated.id,
        project_id=updated.project_id,
        user_id=updated.user_id,
        role=updated.role,
        added_by=updated.added_by,
        added_at=updated.added_at.isoformat(),
        json_str=updated.model_dump_json(),
    )
    logger.info(
        "project_member_im_binding_updated",
        project_id=project_id, user_id=user_id,
        bound=normalized is not None,
    )
    return updated


# ─── ACL ─────────────────────────────────────────────────


def has_role(
    *,
    user_id: str,
    project_id: str,
    required: ProjectMemberRole,
    strict: bool = False,
) -> bool:
    """user 是否在 project 至少持有 required 级别的 role.

    Args:
        strict: True = 无成员记录视为拒绝; False (默认 backward-compat) = 视为允许.
    """
    db = store_module.get_db()
    existing = db.get_project_member(project_id, user_id)
    if existing is None:
        if strict:
            return False
        # backward-compat: 项目无 member 配置时不拦
        any_members = bool(db.list_project_members(project_id))
        return not any_members
    actual = existing.get("role")
    return _ROLE_RANK.get(actual, 0) >= _ROLE_RANK.get(required, 0)


def is_owner(user_id: str, project_id: str) -> bool:
    return has_role(
        user_id=user_id, project_id=project_id, required="owner", strict=True
    )


def can_review(user_id: str, project_id: str, *, strict: bool = False) -> bool:
    """approve/reject skill review 的 ACL 入口."""
    return has_role(
        user_id=user_id,
        project_id=project_id,
        required="reviewer",
        strict=strict,
    )


def can_contribute(
    user_id: str, project_id: str, *, strict: bool = False
) -> bool:
    """submit-for-review / consent sign-reject 的 ACL 入口."""
    return has_role(
        user_id=user_id,
        project_id=project_id,
        required="contributor",
        strict=strict,
    )


__all__ = [
    "ProjectMembershipError",
    "add_member",
    "can_contribute",
    "can_review",
    "get_member",
    "has_role",
    "is_owner",
    "list_members",
    "remove_member",
    "update_im_binding",
    "update_role",
]
