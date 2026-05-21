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
