"""Asset / Chapter / Evidence DTOs.

设计依据 TDD §5.3 (DDL) + types/api.ts (前端镜像).
MVP 内存版 - 生产换 SQLAlchemy ORM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetType = Literal["weekly_report", "tech_design", "adr", "incident"]

AssetStatus = Literal[
    "generating",
    "draft",
    "in_review",
    "approved",
    "published",
    "archived",
]


class AssetMetrics(BaseModel):
    """自评卡 4 指标 (Stage 5 产出)."""

    coverage: float = Field(ge=0.0, le=1.0)
    citation_density: float = Field(ge=0.0, le=1.0)
    slop_score: float = Field(ge=0.0, le=1.0)
    similarity: float = Field(ge=0.0, le=1.0)


class ChapterGeneratedBy(BaseModel):
    """章节生成元信息."""

    model: str
    provider: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Chapter(BaseModel):
    """单章节."""

    id: str
    asset_id: str
    asset_version: int = 1
    order_index: int
    title: str
    content: str  # markdown
    layout: dict = Field(default_factory=dict)
    generated_by: ChapterGeneratedBy | None = None
    regeneration_history: list[dict] = Field(default_factory=list)
    approval_state: Literal["pending", "approved", "rejected"] = "pending"
    redacted_spans: list[dict] = Field(default_factory=list)


class Asset(BaseModel):
    """文档资产 (TDD §5.3 主表)."""

    id: str
    project_id: str
    type: AssetType
    title: str
    status: AssetStatus
    current_version: int = 1
    template_id: str | None = None
    created_by: str
    approval_state: Literal["pending", "approved", "rejected"] = "pending"
    redaction_state: Literal["any_unresolved", "all_confirmed"] = "any_unresolved"
    metrics: AssetMetrics | None = None
    created_at: datetime
    updated_at: datetime


class EvidencePreview(BaseModel):
    """Evidence 内嵌的 Event 摘要 (避免前端额外 GET /events/:id)."""

    event_id: str
    title: str | None = None
    source_type: str  # "github" / "claude_code" / "cursor" / ...
    source_ref: str
    author_name: str | None = None
    author_email: str | None = None
    occurred_at: str  # ISO 8601
    content_excerpt: str  # 截取 ≤ 500 字; 后端用 span_start/end 周围片段
    external_url: str | None = None  # "在源头打开" 链接 (GitHub PR / commit)


class Evidence(BaseModel):
    """Chapter 与 Event 之间的多对多桥接.

    设计依据 TDD §7.2.2 / TaskTechDesign T07 数据流时序.
    """

    id: str
    chapter_id: str
    event_id: str
    event_version: int = 1
    span_start: int  # 在 Chapter.content 中的字符偏移
    span_end: int
    citation_text: str  # 例: "PR #127 由 @alice 合并于 2026-05-21"
    manually_added: bool = False
    stale: bool = False  # 编辑后字符相似度 30-70% 标 stale (PRD §5.4 D1)
    trust_score: float | None = None  # 0-1
    citation_strength: float | None = None  # 派生自 trust_score + corroboration
    event_preview: EvidencePreview
