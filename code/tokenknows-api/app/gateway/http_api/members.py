"""HTTP API · v0.9.0 T66 项目成员管理.

端点:
    GET    /projects/:id/members                列表
    POST   /projects/:id/members                添加 / upsert role (仅 owner)
    PATCH  /projects/:id/members/:user_id       改 role (仅 owner)
    DELETE /projects/:id/members/:user_id       删 (仅 owner)
    GET    /me/memberships                      当前 session 在所有项目的 role

ACL: owner 可改, 其他 role 仅可读.

session: 通过 X-User-Id header (MVP); 缺 → 401.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config.logging import logger
from app.gateway.http_api._session import require_user_id
from app.persistence import store as store_module
from app.schemas.project_member import (
    AddProjectMemberRequest,
    ProjectMember,
    ProjectMembersResponse,
    UpdateMemberImBindingRequest,
    UpdateProjectMemberRoleRequest,
)
from app.services.project import membership

router = APIRouter(tags=["members"])


@router.get(
    "/projects/{project_id}/members",
    response_model=ProjectMembersResponse,
)
async def list_members(project_id: str) -> ProjectMembersResponse:
    """公开查询: 任何已登录用户可看. ACL 留在写操作上."""
    items = membership.list_members(project_id)
    return ProjectMembersResponse(
        project_id=project_id,
        items=items,
        owner_count=sum(1 for m in items if m.role == "owner"),
        reviewer_count=sum(1 for m in items if m.role == "reviewer"),
        contributor_count=sum(1 for m in items if m.role == "contributor"),
    )


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMember,
    status_code=201,
)
async def add_member_endpoint(
    project_id: str,
    body: AddProjectMemberRequest,
    actor_id: str = Depends(require_user_id),
) -> ProjectMember:
    """添加成员. 仅 owner 可操作 (空项目 bootstrap 例外).

    Bootstrap: 项目无任何 member 时, 第一个调用者自动成为 owner
    (规避 鸡生蛋: 没 owner 就没人能创建第一个 owner).
    v1.0.1: bootstrap 加进程内锁防止并发请求让 2 个用户同时成 owner.
    """
    # 先在锁外快速判: 大部分调用是非 bootstrap 路径, 不进锁省并发开销
    existing = membership.list_members(project_id)
    if not existing:
        # bootstrap: 进入锁内再读一次 (double-check)
        with membership._bootstrap_lock:  # noqa: SLF001
            existing = membership.list_members(project_id)
            if not existing:
                # 强制 actor 成为 owner, 忽略 body.role
                return membership.add_member(
                    project_id=project_id,
                    user_id=actor_id,
                    role="owner",
                    added_by=actor_id,
                    note="(auto-bootstrap owner)",
                )
            # else: 已有他人 bootstrap 成功, 走非 bootstrap 路径 (下面)
    # 非 bootstrap 路径: 必须 owner
    if not membership.is_owner(actor_id, project_id):
        raise HTTPException(403, detail="Only project owner can add members")
    try:
        return membership.add_member(
            project_id=project_id,
            user_id=body.user_id,
            role=body.role,
            added_by=actor_id,
            note=body.note,
        )
    except Exception as e:
        logger.error(
            "add_member_failed",
            project_id=project_id, user_id=body.user_id, error=str(e),
        )
        raise HTTPException(500, detail=str(e)) from e


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    response_model=ProjectMember,
)
async def update_role_endpoint(
    project_id: str,
    user_id: str,
    body: UpdateProjectMemberRoleRequest,
    actor_id: str = Depends(require_user_id),
) -> ProjectMember:
    """改 role. 仅 owner 可操作; 拒绝降最后一个 owner."""
    if not membership.is_owner(actor_id, project_id):
        raise HTTPException(
            403, detail="Only project owner can update member role"
        )
    try:
        return membership.update_role(
            project_id=project_id,
            user_id=user_id,
            new_role=body.role,
            actor_id=actor_id,
        )
    except membership.ProjectMembershipError as e:
        raise HTTPException(409, detail=str(e)) from e


@router.patch(
    "/projects/{project_id}/members/{user_id}/im-binding",
    response_model=ProjectMember,
)
async def update_member_im_binding_endpoint(
    project_id: str,
    user_id: str,
    body: UpdateMemberImBindingRequest,
    actor_id: str = Depends(require_user_id),
) -> ProjectMember:
    """T130.4 · 自助绑定 / 解绑飞书 open_id.

    ACL: 用户自己改自己 (actor_id == user_id) OR owner 可代改.
    传 None / 空字符串 → 解绑.
    """
    if actor_id != user_id and not membership.is_owner(actor_id, project_id):
        raise HTTPException(
            403,
            detail="Only the member themself or project owner can update IM binding",
        )
    try:
        return membership.update_im_binding(
            project_id=project_id,
            user_id=user_id,
            im_feishu_open_id=body.im_feishu_open_id,
        )
    except membership.ProjectMembershipError as e:
        raise HTTPException(404, detail=str(e)) from e


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=204,
)
async def remove_member_endpoint(
    project_id: str,
    user_id: str,
    actor_id: str = Depends(require_user_id),
) -> None:
    """删成员. 仅 owner; 拒绝删最后 owner."""
    if not membership.is_owner(actor_id, project_id):
        raise HTTPException(
            403, detail="Only project owner can remove members"
        )
    try:
        ok = membership.remove_member(project_id, user_id)
    except membership.ProjectMembershipError as e:
        raise HTTPException(409, detail=str(e)) from e
    if not ok:
        raise HTTPException(404, detail="Member not found")
    return None


@router.get("/me/memberships")
async def list_my_memberships(
    actor_id: str = Depends(require_user_id),
) -> dict[str, list[dict]]:
    """跨项目: 我在哪些项目里, 各是什么 role.

    返 {'items': [{'project_id', 'role', ...}]} (不用 Pydantic 类型,
    直接 JSON; UI 用 store.list_user_project_memberships 的 dump)
    """
    db = store_module.get_db()
    items = db.list_user_project_memberships(actor_id)
    return {"items": items}
