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

    # 数据源数: 用 datasource_health (近 7 天) DISTINCT, 不再 limit=100 抽样
    health_rows = db.datasource_health(project_id, window_days=7)
    datasources_total = max(len([r for r in health_rows if r["event_count"] > 0]), 1)

    return {
        "events_this_week": total_week,
        "assets_pending_review": pending,
        "datasources_total": datasources_total,
        "datasources_healthy": datasources_total,  # MVP: 假设全 healthy
    }


# ─── 数据源健康度 (5 源真实数 + last_seen) ────────────────────────


_KNOWN_SOURCE_TYPES = ("claude_code", "github", "cursor", "vscode", "local_file")


@router.get("/projects/{project_id}/datasources/health")
async def get_datasource_health(
    project_id: str,
    window_days: int = Query(30, ge=1, le=365),
) -> dict:
    """T03 · 工作台数据源卡 · 每个 source_type 的事件数 + 最近一次入库.

    返回 5 行 (包含未出现过的源, event_count=0), 前端按固定顺序排:
        claude_code / github / cursor / vscode / local_file

    health 判定 (前端展示用):
        - active   : last_seen_at within 24h
        - stale    : last_seen_at within 7d
        - cold     : last_seen_at within window_days
        - inactive : 无事件 (event_count = 0)
    """
    from datetime import datetime, timezone
    from app.persistence import get_db
    db = get_db()
    rows = db.datasource_health(project_id, window_days=window_days)

    # 已出现的源
    by_type = {r["source_type"]: r for r in rows}
    now = datetime.now(timezone.utc)

    def _health(last_seen: str | None, count: int) -> str:
        if count == 0 or not last_seen:
            return "inactive"
        try:
            ts = last_seen.replace("Z", "+00:00") if last_seen.endswith("Z") else last_seen
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hours_ago = (now - dt).total_seconds() / 3600
        except ValueError:
            return "cold"
        if hours_ago <= 24:
            return "active"
        if hours_ago <= 24 * 7:
            return "stale"
        return "cold"

    # 补齐 5 个已知源 (含历史有数据但近期无活动的源)
    items: list[dict] = []
    for st in _KNOWN_SOURCE_TYPES:
        r = by_type.get(st)
        ec = r["event_count"] if r else 0          # 窗口内
        te = r["total_events"] if r else 0          # 历史
        ls = r["last_seen_at"] if r else None
        li = r["last_ingested_at"] if r else None
        # health: 优先看 last_ingested_at (插件是否还在跑) — 24h 内入库就算 active
        health = _health(li or ls, te)
        items.append({
            "source_type": st,
            "event_count": ec,
            "total_events": te,
            "last_seen_at": ls,
            "last_ingested_at": li,
            "health": health,
        })

    total_active = sum(1 for it in items if it["health"] in ("active", "stale"))
    total_events_window = sum(it["event_count"] for it in items)
    total_events_all = sum(it["total_events"] for it in items)
    return {
        "items": items,
        "window_days": window_days,
        "total_active": total_active,
        "total_events_window": total_events_window,
        "total_events_all": total_events_all,
    }
