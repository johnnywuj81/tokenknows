"""HTTP API · Projects list / detail (T141).

之前这俩 endpoint 一直靠 frontend MSW SW mock, SW 一旦失效整个工作台
永远 loading. 落到 backend 真路径后, 不再依赖 dev-only mock.

端点:
    GET /projects              list (附带 stats / health)
    GET /projects/{id}         detail (附带 stats / health)

数据来源:
    - 元数据 hardcode (跟前端 fixtureProjects 对齐), 后续多项目时改 DB 表
    - stats 子字段从 events / generation 实时算

T144 修复 code-review 发现的 4 个问题:
  - HIGH-1: async def → def 避免 sync DB call 阻塞 event loop
  - HIGH-4: except Exception 加 logger.warning + exc_info 不再 silently swallow
  - MEDIUM-3: _PROJECT_METADATA 改 MappingProxyType + Final 防止意外 mutation
  - MEDIUM-4: datasources_healthy 真算 (按 health=="healthy" 过滤), 不再硬编码 = total
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Final, Mapping

from fastapi import APIRouter, HTTPException

from app.persistence import store as store_module
from app.schemas.project import Project, ProjectStats
from app.services import generation_service as gen_svc

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── 元数据 (跟 web fixtureProjects 对齐, 用 MappingProxyType 防 mutation) ──


_PROJECT_METADATA: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType({
    "proj-demo-001": MappingProxyType({
        "id": "proj-demo-001",
        "name": "TokenKnows 自身研发",
        "description": "内部 dogfooding 项目, 沉淀产品本身的研发过程。",
        "owner_id": "user-001",
        "llm_egress_enabled": False,
        "task_egress_config": {},
        "custom_redaction_terms": [],
        "brand_theme": {},
        "created_at": "2026-05-19T10:00:00Z",
        "updated_at": "2026-05-20T10:00:00Z",
        "role": "owner",
        "health": "healthy",
    }),
})


# ─── stats 实时算 ────────────────────────────────────────────────────


def _compute_stats(project_id: str) -> ProjectStats:
    db = store_module.get_db()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    _rows, total_week = db.list_events(
        project_id=project_id, from_iso=week_ago, limit=1,
    )

    try:
        assets = gen_svc.list_assets(project_id)
        pending = sum(1 for a in assets if a.status == "in_review")
    except Exception:  # noqa: BLE001 — defensive: generation service down 不影响 list
        # T144: 之前只 swallow, programming error 时无任何日志痕迹. 改为 warn
        # + 完整 stack trace, 仍 fallback 到 0 不影响 endpoint 可用性.
        logger.warning(
            "list_assets failed for project %s; defaulting pending=0",
            project_id, exc_info=True,
        )
        pending = 0

    health_rows = db.datasource_health(project_id, window_days=7)
    # T144: datasources_total = 有事件的 source 数, datasources_healthy = 其中
    # 真正 health=="healthy" 的数. 之前硬编码 healthy = total 让前端无法显示
    # 降级状态. 跟 web Project.health "healthy/degraded/down" 语义对齐.
    active_sources = [r for r in health_rows if r["event_count"] > 0]
    datasources_total = max(len(active_sources), 1)
    datasources_healthy = sum(
        1 for r in active_sources if r.get("health") == "healthy"
    )

    return ProjectStats(
        events_this_week=total_week,
        assets_pending_review=pending,
        datasources_total=datasources_total,
        datasources_healthy=datasources_healthy,
    )


def _build_project(meta: Mapping[str, Any]) -> Project:
    return Project(**meta, stats=_compute_stats(meta["id"]))


# ─── endpoints ────────────────────────────────────────────────────────
#
# T144 (HIGH-1): handlers 是 def 而非 async def. _compute_stats 内部走同步
# SQLite query (db.list_events / db.datasource_health) + 同步 gen_svc.list_assets,
# 在 async def 里跑会阻塞 FastAPI event loop, 高并发下卡死所有请求.
# FastAPI 看到 sync handler 会自动放进 threadpool 跑, 不阻塞 loop.


@router.get("/projects", response_model=list[Project])
def list_projects() -> list[Project]:
    """T141 · 工作台 ProjectSwitcher / ProjectsListPage 拉取所有项目."""
    return [_build_project(meta) for meta in _PROJECT_METADATA.values()]


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    """T141 · WorkbenchPage 拉单项目元数据 + stats."""
    meta = _PROJECT_METADATA.get(project_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"project not found: {project_id}")
    return _build_project(meta)
