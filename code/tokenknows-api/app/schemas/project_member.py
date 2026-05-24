"""ProjectMember · v0.9.0 T65 项目成员 + 角色.

替换 v0.5/v0.6 trust-on-faith 的 user_id-in-body 模式;
endpoints 通过 ACL 校验当前 session user 在该 project 的 role.

Role 语义:
- owner: 1 个 / project (创建者); 可改成员 role / 删项目
- reviewer: N 个 / project; 可 approve/reject skill review
- contributor: M 个 / project; 可 submit skill for review / consent sign/reject

Owner 隐含拥有 reviewer + contributor 全部权限.
Reviewer 隐含拥有 contributor 权限.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectMemberRole = Literal["owner", "reviewer", "contributor"]


class ProjectMember(BaseModel):
    """项目成员单条记录 (项目 × user × role)."""

    id: str
    """member-{uuid} 12 hex."""
    project_id: str
    user_id: str
    """platform user_id (open_id / userid / 邮箱).

    与 IM consent 的 user_id 同义; v1.0 之前不强制和 Auth user 1-1 映射.
    """
    role: ProjectMemberRole
    added_by: str
    """添加者 user_id (审计追溯)."""
    added_at: datetime
    note: str | None = Field(default=None, max_length=200)
    # T130.4 · 飞书 open_id 自助绑定 (放宽 reject_notifier 必须 author='ou_xxx' 限制).
    # 现实里 asset.created_by 多是邮箱/用户名, 通过这个字段反查真实 IM 身份.
    # 持久化在 ProjectMember JSON blob (无 schema 迁移).
    im_feishu_open_id: str | None = Field(
        default=None,
        max_length=128,
        description="飞书 open_id (形如 ou_xxx); 用于退回 DM 通知路由",
    )


# ─── 请求 / 响应 DTO ──────────────────────────────────────────────


class AddProjectMemberRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    role: ProjectMemberRole = "contributor"
    note: str | None = Field(default=None, max_length=200)


class UpdateProjectMemberRoleRequest(BaseModel):
    role: ProjectMemberRole


class UpdateMemberImBindingRequest(BaseModel):
    """T130.4 · 自助更新 IM 绑定. None / 空字符串 → 解绑."""

    im_feishu_open_id: str | None = Field(default=None, max_length=128)


class ProjectMembersResponse(BaseModel):
    project_id: str
    items: list[ProjectMember] = Field(default_factory=list)
    owner_count: int
    reviewer_count: int
    contributor_count: int
