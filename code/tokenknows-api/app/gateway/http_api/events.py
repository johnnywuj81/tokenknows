"""HTTP API · 研发事件接入 + 查询.

端点:
    POST /projects/:id/events             插件批量上报
    GET  /projects/:id/events             工作台事件流
    GET  /events/:id                      事件详情抽屉
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.event import (
    Event,
    EventIngestRequest,
    EventIngestResponse,
    PaginatedEvents,
)
from app.services import event_service as svc

router = APIRouter()


@router.post(
    "/projects/{project_id}/events",
    response_model=EventIngestResponse,
    status_code=201,
)
async def ingest_events(
    project_id: str, body: EventIngestRequest
) -> EventIngestResponse:
    """T04+ · 插件批量上报研发事件.

    幂等保证: 同 (project_id, content_hash) 已存在则跳过.
    """
    if not body.events:
        raise HTTPException(400, detail="events 不能为空")
    if len(body.events) > 500:
        raise HTTPException(400, detail="单次最多 500 条")
    return svc.ingest_events(project_id, body.events)


@router.get(
    "/projects/{project_id}/events",
    response_model=PaginatedEvents,
)
async def list_events(
    project_id: str,
    source_type: str | None = Query(default=None),
    from_iso: str | None = Query(default=None, alias="from"),
    to_iso: str | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedEvents:
    """T03 · 工作台事件流; 按 occurred_at desc 分页."""
    events, meta = svc.list_events(
        project_id=project_id,
        source_type=source_type,
        from_iso=from_iso,
        to_iso=to_iso,
        cursor=cursor,
        limit=limit,
    )
    return PaginatedEvents(data=events, meta=meta)


@router.get("/events/{event_id}", response_model=Event)
async def get_event(event_id: str) -> Event:
    """T04 · 事件详情抽屉."""
    ev = svc.get_event(event_id)
    if ev is None:
        raise HTTPException(404, detail="Event not found")
    return ev


# ─── T03 · 项目统计 ───────────────────────────────────────────


from datetime import datetime, timedelta, timezone  # noqa: E402

from app.persistence import get_db  # noqa: E402
from app.services import generation_service as gen_svc  # noqa: E402


@router.get("/projects/{project_id}/stats")
async def get_project_stats(project_id: str) -> dict:
    """T03 · 工作台 4 个数字卡: 本周事件 / 待审文档 / 数据源.

    - events_this_week: 真实查 events 表 (occurred_at >= now - 7d)
    - assets_pending_review: 真实从 in-memory _assets 数 status=in_review
    - datasources_total / healthy: 当前用 fixture (4 个 source_type 区分)
    """
    db = get_db()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    events_this_week, _ = db.list_events(
        project_id=project_id, from_iso=week_ago, limit=1
    )
    # _ 是 list_events 返 list[Event] 取空但 total 走第 2 返回值
    rows, total_week = db.list_events(
        project_id=project_id, from_iso=week_ago, limit=1,
    )

    assets = gen_svc.list_assets(project_id)
    pending = sum(1 for a in assets if a.status == "in_review")

    # 数据源数: 统计本项目近 7 天事件出现的 source_type 数量
    source_types = set()
    sample_events, _ = db.list_events(project_id=project_id, from_iso=week_ago, limit=100)
    for e in sample_events:
        st = e.get("source_type")
        if st:
            source_types.add(st)
    datasources_total = max(len(source_types), 1)

    return {
        "events_this_week": total_week,
        "assets_pending_review": pending,
        "datasources_total": datasources_total,
        "datasources_healthy": datasources_total,  # MVP: 假设全 healthy
    }
