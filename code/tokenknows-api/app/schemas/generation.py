"""文档生成流水线 5 阶段 DTOs.

设计依据 Architecture.md §4.3.3 数据流 3 (文档生成 5 阶段).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.asset import AssetType

# ─── 请求 ────────────────────────────────────────────────────────


class GenerateAssetRequest(BaseModel):
    """POST /api/v1/projects/{id}/assets/generate 入参."""

    type: AssetType
    time_window: str = Field(
        default="this_week",
        description="本周 / 上周 / last_7_days / last_14_days / last_30_days",
    )
    source_filter: dict | None = Field(
        default=None,
        description="按 source_type / author / tag 过滤",
    )
    model_override: str | None = Field(
        default=None,
        description="T08 用户切换模型场景. None = 用 task 默认",
    )
    provider_override: str | None = Field(
        default=None,
        description="None = 用 task 默认",
    )
    topic_hint: str | None = Field(
        default=None,
        description=(
            "用户主题提示, 用于:\n"
            "  1) collect 阶段对 events 做关键词预过滤 (大小写不敏感子串匹配)\n"
            "  2) outline / distill prompt 中明确告知 LLM '仅围绕该主题展开'.\n"
            "对 agent_skill 类型尤其重要 (单一主题才能蒸馏出可用 SKILL.md)."
        ),
        max_length=200,
    )


# ─── 进度跟踪 ────────────────────────────────────────────────────

StageName = Literal["collect", "outline", "content", "evidence", "assess"]
StageStatusEnum = Literal["pending", "running", "done", "failed", "skipped"]


class StageStatus(BaseModel):
    """单个阶段的状态."""

    name: StageName
    status: StageStatusEnum
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    # 阶段产出元数据 (示例):
    #   collect: { candidates_count: 50, trust_score_avg: 0.72 }
    #   outline: { chapters_total: 5 }
    #   content: { chapters_completed: 3, current_chapter: "关键决策" }
    #   evidence: { evidence_total: 24, evidence_stale: 0 }
    #   assess: { coverage: 0.84, ... }
    metadata: dict = Field(default_factory=dict)


class GenerationProgress(BaseModel):
    """整体生成进度 (前端 polling / SSE 拿).

    设计依据 TaskTechDesign T06 数据流时序 + 任务包 T06 5 阶段进度条.
    """

    asset_id: str
    overall_status: Literal["pending", "running", "done", "failed"]
    current_stage: StageName | None = None
    stages: list[StageStatus]
    started_at: datetime
    updated_at: datetime
    # 生成全程使用的 LLM (出于审计 / UI "由 X 模型生成" 标注)
    primary_provider: str | None = None
    primary_model: str | None = None
    fallback_used: bool = False
    error: str | None = None


# ─── SSE 事件 (W4D17 后端 → 前端) ────────────────────────────────


class SseEvent(BaseModel):
    """SSE 事件包络."""

    event: Literal[
        "stage_started",
        "stage_completed",
        "chapter_completed",
        # v0.2 · book 长文档专属
        "volume_outline_completed",     # 卷大纲生成完
        "chapter_outline_completed",    # 单卷内的章大纲生成完
        "done",
        "failed",
    ]
    asset_id: str
    stage: StageName | None = None
    payload: dict = Field(default_factory=dict)
    ts: datetime
