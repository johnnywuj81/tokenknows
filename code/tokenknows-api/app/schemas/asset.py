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
