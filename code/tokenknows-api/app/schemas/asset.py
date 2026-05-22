"""Asset / Chapter / Evidence DTOs.

设计依据 TDD §5.3 (DDL) + types/api.ts (前端镜像).
MVP 内存版 - 生产换 SQLAlchemy ORM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# v0.2 升级: 加 book (书籍长文) + agent_skill (蒸馏出的专家技能)
AssetType = Literal["weekly_report", "tech_design", "adr", "incident", "book", "agent_skill"]

AssetStatus = Literal[
    "generating",
    "draft",
    "in_review",
    "approved",
    "published",
    "archived",
]


class AssetMetrics(BaseModel):
    """自评卡指标 (Stage 5 产出).

    v0.2 升级: 加 consistency_score (仅 book 类型, 跨章节连贯度).
    """

    coverage: float = Field(ge=0.0, le=1.0)
    citation_density: float = Field(ge=0.0, le=1.0)
    slop_score: float = Field(ge=0.0, le=1.0)
    similarity: float = Field(ge=0.0, le=1.0)
    consistency_score: float | None = Field(default=None, ge=0.0, le=1.0)
    """v0.2 · book 跨章节连贯度 (相邻章节 cosine 均值); 其它类型为 None."""


class ChapterGeneratedBy(BaseModel):
    """章节生成元信息."""

    model: str
    provider: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Chapter(BaseModel):
    """单章节.

    v0.2 升级: 加 parent_id / depth 支持 book 类嵌套大纲;
              加 applied_skills 追踪 skill 应用历史 (Milestone C).

    向后兼容: 4 类现有文档全部 parent_id=None / depth=0 / applied_skills=[].
    """

    id: str
    asset_id: str
    asset_version: int = 1
    order_index: int
    parent_id: str | None = None         # v0.2: book 嵌套 (NULL=顶层)
    depth: int = 0                       # v0.2: 0=卷, 1=章, 2=节 (book 才用 >0)
    title: str
    content: str  # markdown
    layout: dict = Field(default_factory=dict)
    generated_by: ChapterGeneratedBy | None = None
    regeneration_history: list[dict] = Field(default_factory=list)
    applied_skills: list[dict] = Field(default_factory=list)  # v0.2: [{skill_id, version, applied_at}]
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


# ─── T10 · 脱敏 ─────────────────────────────────────────────────


class RedactionItem(BaseModel):
    """T10 单条命中: 章节内某字符 span 的敏感内容."""

    id: str
    chapter_id: str
    span_start: int
    span_end: int
    type: str                # 'EMAIL' / 'API_KEY' / 'IP' / 'INTERNAL'
    matched_text: str        # 真匹配文本 (前端可能脱敏显示)
    rule_source: str = "rule"  # 'rule' / 'llm' / 'custom'
    suggested_replacement: str  # 默认替换占位符
    status: str = "pending"  # 'pending' / 'confirmed' / 'exempted'
    context_before: str | None = None
    context_after: str | None = None
    reason: str | None = None  # 豁免理由


class RedactionScanJob(BaseModel):
    """T10 扫描 job (MVP 同步返回 status=done)."""

    job_id: str
    asset_id: str
    status: str  # 'pending' / 'running' / 'done' / 'failed'
    progress: float = 1.0  # 0-1
    items: list[RedactionItem]


# ─── T11/T12 · 发布 ─────────────────────────────────────────────


class PublishRecord(BaseModel):
    """T11/T12 单条发布记录 (asset → 渠道)."""

    id: str
    asset_id: str
    asset_version: int
    destination: str           # 'internal' / 'public_link' / 'export_md'
    destination_ref: str | None  # e.g. "/internal/asset/xxx" / public url token / file path
    publish_mode: str          # 'full' / 'summary_with_backlink'
    status: str                # 'pending' / 'success' / 'failed' / 'revoked'
    url: str | None
    published_at: str          # ISO 8601
    published_by: str
    visibility: str | None = None  # 公开链接时: 'team' / 'public'
    error: str | None = None       # status=failed 时
