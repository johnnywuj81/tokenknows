"""Project schema · T141 · 工作台 list/detail endpoint 用.

之前 GET /projects / GET /projects/:id 一直靠前端 MSW mock,
SW 一抖整个 UI 就 loading 永远不出来. 把这俩落到 backend
真路径, 不再依赖 dev-only mock.

数据策略:
  - 元数据 (id/name/description/owner_id 等) hardcode 在 router 里
    (跟前端 fixtureProjects 完全一致); 后续真要多项目时再上 DB.
  - stats 子字段从 events 表实时算 (mirror /projects/:id/stats).
  - health/role 现阶段固定值 (没有真 RBAC).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectStats(BaseModel):
    events_this_week: int = 0
    assets_pending_review: int = 0
    datasources_total: int = 0
    datasources_healthy: int = 0


ProjectHealth = Literal["healthy", "degraded", "down"]
ProjectRole = Literal["owner", "reviewer", "member", "viewer"]


class Project(BaseModel):
    """v1.0+ 工作台 ProjectSwitcher / ProjectsListPage / WorkbenchPage 期望的 shape.

    跟 web/src/types/api.ts 的 `Project` interface 字段对齐.
    """

    id: str
    name: str
    description: str | None = None
    owner_id: str
    llm_egress_enabled: bool = False
    task_egress_config: dict[str, bool] = Field(default_factory=dict)
    custom_redaction_terms: list[dict[str, Any]] = Field(default_factory=list)
    brand_theme: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    # 衍生字段 (响应附带)
    role: ProjectRole | None = None
    health: ProjectHealth | None = None
    stats: ProjectStats | None = None
