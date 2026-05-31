"""Event schema · 研发事件 (插件采集 → 知识资产候选).

来源: PRD §7.2.1 / TDD §5.2 · events 表
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventSourceType = Literal[
    "claude_code",
    "claude_cowork",  # v2.0 T117 · Claude Cowork plugin 上报
    "codex",          # v2.1 · OpenAI Codex CLI/Desktop rollout 采集
    "cursor",
    "vscode",
    "github",
    "local_file",
    "manual",
]

EventType = Literal[
    "ai_conversation_turn",
    "tool_call",
    "code_change",
    "pr_event",
    "issue_event",
    "commit",
    "local_document",
    "manual_note",
]


class EventAuthor(BaseModel):
    name: str
    email: str | None = None
    external_id: str | None = None


class EventCreate(BaseModel):
    """插件上报的事件 (写入用; id/ingested_at 由服务端填)."""

    source_type: EventSourceType
    source_ref: str
    external_id: str            # 同源唯一 (e.g. Claude Code uuid)
    version: int = 1
    event_type: EventType
    occurred_at: datetime
    author: EventAuthor | None = None
    title: str | None = None
    content: str                # 原文 (脱敏前)
    payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: str           # SHA-256(content) - 用于去重
    tags: list[str] = Field(default_factory=list)
    # 插件按 source 算的 trust_score (0-1).
    # 分量在 payload.trust_components: {source_authority, extraction_confidence}
    trust_score: float | None = None


class Event(EventCreate):
    """服务端持久化后的完整事件 (读出去)."""

    id: str
    project_id: str
    ingested_at: datetime
    redaction_state: Literal["raw", "screened", "confirmed", "exported"] = "raw"
    is_private: bool = False             # PRD §5.4 D2 敏感来源遮蔽


class EventIngestRequest(BaseModel):
    """POST /projects/:id/events body."""

    events: list[EventCreate]


class EventIngestResponse(BaseModel):
    """ingest 结果: 新增了几条, 跳过几条 (重复)."""

    ingested: int
    skipped: int                # content_hash 已存在
    event_ids: list[str]


class PaginatedEvents(BaseModel):
    """GET /projects/:id/events 响应 (与 frontend useInfiniteQuery 一致)."""

    data: list[Event]
    meta: dict[str, Any]        # {total, cursor, has_more}
