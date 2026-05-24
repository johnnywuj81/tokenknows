"""Event → ValueSegment 提炼链路 · T131 MVP.

把 plugin 上报的 events (Claude Code / Cowork / 未来 IDE 插件) 简单提炼
成 ValueSegment, 让现有蒸馏管线 (collect → evidence stage) 用统一的
value_segments 抽象消费, 不再"events 一类、im_chat 一类"两套.

MVP 规则 (足够简单, 不接 LLM):
  · 过滤: trust_score < _MIN_TRUST 或 content < _MIN_CONTENT_CHARS → 跳过
  · 映射: 1 event = 1 ValueSegment (不做相邻合并; v1.5 可加)
  · 幂等: segment_id = f"seg-evt-{event.id}", 用 ON CONFLICT(id) DO UPDATE
    保证同事件多次提炼不产生重复段

不在 MVP scope (留 v1.5+):
  · LLM-driven 摘要 / 改写 (现在 segment.content == event.content)
  · 跨 event 合并 (e.g. 同 source_ref 内事件 → 单段)
  · 后台调度器 (现在 inline 在 ingest_events 内跑, 单次最多 100 events 不痛)
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.event import Event
from app.schemas.im import ValueSegment, ValueSegmentSource


# 过滤阈值: trust_score 缺省按 0.5 (中等), 低于这个值的事件不入 segment
_MIN_TRUST = 0.3
# content 至少 20 字符才有"价值" (避免空 / "ok" 这种废段)
_MIN_CONTENT_CHARS = 20


def event_to_segment(event: Event) -> ValueSegment | None:
    """单 event → ValueSegment (纯函数, 不写库). 返 None 表示该 event 被过滤.

    幂等性靠 deterministic id 实现: seg-evt-{event.id}.

    Filter rules:
      - trust_score < _MIN_TRUST → skip (低信号)
      - len(content.strip()) < _MIN_CONTENT_CHARS → skip (太短无价值)
    """
    trust = event.trust_score if event.trust_score is not None else 0.5
    if trust < _MIN_TRUST:
        return None
    content = (event.content or "").strip()
    if len(content) < _MIN_CONTENT_CHARS:
        return None

    return ValueSegment(
        id=f"seg-evt-{event.id}",
        project_id=event.project_id,
        source=ValueSegmentSource(
            type="event",
            event_id=event.id,
            # contributors 从 event.author 翻译 (单作者)
            contributors=[],  # MVP 不填; 真要做的话给 ValueSegmentSource 加从 EventAuthor 转
        ),
        content=content,
        trust_score=trust,
        extracted_at=datetime.now(timezone.utc),
    )


def process_events_to_segments(
    project_id: str, events: list[Event]
) -> list[ValueSegment]:
    """批量 events → 写 value_segments 表; 返回真正写入的 segments.

    幂等: 同 event 多次跑只产生 1 个 segment (ON CONFLICT id 更新).
    任何 event 转换失败 swallow + log, 不阻断其它 events.
    """
    if not events:
        return []
    db = get_db()
    written: list[ValueSegment] = []
    skipped_filter = 0
    skipped_error = 0
    for ev in events:
        try:
            seg = event_to_segment(ev)
            if seg is None:
                skipped_filter += 1
                continue
            db.upsert_value_segment(
                segment_id=seg.id,
                project_id=seg.project_id,
                source_type=seg.source.type,
                trust_score=seg.trust_score,
                extracted_at=seg.extracted_at.isoformat(),
                json_str=seg.model_dump_json(),
            )
            written.append(seg)
        except Exception as exc:  # noqa: BLE001
            skipped_error += 1
            logger.warning(
                "event_to_segment_failed",
                event_id=getattr(ev, "id", "?"),
                project_id=project_id,
                error=str(exc),
            )
    logger.info(
        "events_to_segments_processed",
        project_id=project_id,
        input=len(events),
        written=len(written),
        skipped_filter=skipped_filter,
        skipped_error=skipped_error,
    )
    return written


__all__ = [
    "event_to_segment",
    "process_events_to_segments",
]
