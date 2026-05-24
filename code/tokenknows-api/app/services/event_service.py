"""Event ingestion + 查询服务.

设计:
- ingest_events 是幂等的: 同 project_id + content_hash 已存在 → 跳过, 不重复
- 内存层不缓存事件 (events 表可能很大), 全部走 SQLite 查
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.event import (
    Event,
    EventCreate,
    EventIngestResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_events(
    project_id: str, payload: list[EventCreate]
) -> EventIngestResponse:
    """批量入库. 已存在 content_hash 跳过.

    T131: 入库成功的 events 同步触发 → value_segment 提炼 (filter +
    persist). 提炼失败不影响 ingest 主流程 (异常 swallow).
    """
    db = get_db()
    now = _now().isoformat()
    ingested_ids: list[str] = []
    ingested_events: list[Event] = []
    skipped = 0

    for ev in payload:
        event_id = f"evt-{uuid4().hex[:12]}"
        full = Event(
            **ev.model_dump(),
            id=event_id,
            project_id=project_id,
            ingested_at=_now(),
        )
        added = db.upsert_event(
            event_id=event_id,
            project_id=project_id,
            source_type=full.source_type,
            event_type=full.event_type,
            occurred_at=full.occurred_at.isoformat(),
            ingested_at=now,
            content_hash=full.content_hash,
            json_str=full.model_dump_json(),
        )
        if added:
            ingested_ids.append(event_id)
            ingested_events.append(full)
        else:
            skipped += 1

    logger.info(
        "events_ingested",
        project_id=project_id,
        ingested=len(ingested_ids),
        skipped=skipped,
        total_incoming=len(payload),
    )

    # T131 · 异步风格 (实为 sync 单线程, 失败 swallow): 触发提炼.
    # 走延迟 import 避免在事件子系统启动早期就引入 value_segment 依赖.
    if ingested_events:
        try:
            from app.services import event_value_segment_service
            event_value_segment_service.process_events_to_segments(
                project_id, ingested_events,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event_value_segment_extraction_failed",
                project_id=project_id,
                error=str(exc),
            )

    return EventIngestResponse(
        ingested=len(ingested_ids),
        skipped=skipped,
        event_ids=ingested_ids,
    )


def list_events(
    project_id: str,
    source_type: str | None = None,
    from_iso: str | None = None,
    to_iso: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Event], dict]:
    """查询事件 (游标分页)."""
    db = get_db()
    raws, total = db.list_events(
        project_id=project_id,
        source_type=source_type,
        from_iso=from_iso,
        to_iso=to_iso,
        cursor=cursor,
        limit=limit,
    )
    events = [Event.model_validate(r) for r in raws]
    next_cursor = events[-1].occurred_at.isoformat() if len(events) == limit else None
    meta = {
        "total": total,
        "cursor": next_cursor,
        "has_more": next_cursor is not None,
    }
    return events, meta


def get_event(event_id: str) -> Event | None:
    raw = get_db().get_event(event_id)
    if raw is None:
        return None
    return Event.model_validate(raw)
