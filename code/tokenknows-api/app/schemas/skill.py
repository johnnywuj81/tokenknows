"""Skill schema · 蒸馏出的 Agent 专家技能 (v0.2 升级).

设计依据:
- PRD §5.8 Skill 自进化机制 (H1-H5)
- TDD §5.3 skills 表 + §7.5/7.6 Skill 注入 / 反馈 hook
- Anthropic SKILL.md 格式 (YAML frontmatter + 正文)
- 项目级私有 (MVP 范围)

数据流:
    distill (从 chapters 抽取) → Skill(status=draft)
        ↓ 人工审批
    Skill(status=active) → 被 _stage_content 注入 system_prompt
        ↓ chapter 被 approve/reject/regenerate
    on_chapter_state_changed → 更新 usage_count / acceptance_count / trust_score
        ↓ usage>=20 && acc_rate<0.5
    evolve_skill_v2 → Skill(version=2, distilled_from=旧 chapters)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SkillStatus = Literal[
    # v0.2 - v0.4 既有
    "draft",       # 刚蒸馏出来, 待审批 (手动蒸馏 / 全员签字后转入)
    "active",      # 正式可被注入下游生成
    "deprecated",  # 已停用 (人工或自动)
    "locked",      # 固化版本 (不再参与自进化; 与 Skill.locked 区分: 字段 vs 状态)
    # v0.5.1 新增 (Q5 contributor 个人同意闸门)
    "pending_contributor_consent",  # 自动蒸馏出来 contributors 非空, 等所有人签
    "rejected_by_contributor",      # 任一 contributor 拒绝, 冻结归档
    "expired_no_consent",           # 30 天无人响应, 自动归档
]


# ─── v0.5.1 · Consent (Q5 决策落地) ───────────────────────────────


class ConsentRecord(BaseModel):
    """单条 contributor 同意 / 拒绝记录.

    Skill.consent_signed_by 是 list[ConsentRecord];
    Skill.consent_rejected_by 是 单个 ConsentRecord | None (首位拒绝者冻结).
    """

    user_id: str
    """contributor 的 platform user_id (open_id / userid)."""

    signed_at: datetime
    """签字 / 拒绝时刻 (UTC)."""

    channel: Literal["im_dm", "web"]
    """signed 的渠道: im_dm = IM 私聊卡片;web = 站内 Notification Bell."""

    note: str | None = None
    """可选备注 (拒绝时常用, 如 '此聊天属于人事讨论不宜蒸馏')."""


class SkillMetrics(BaseModel):
    """Skill 自进化指标 (实时更新).

    trust_score = (acceptance_count + 1) / (acceptance_count + rejection_count + 2)
                * recency_decay(last_used_at)
                * usage_confidence(usage_count)

    详见 TDD §7.6 evolve_skill_v2.
    """

    usage_count: int = 0
    """被注入到 prompt 的累计次数 (每次 _stage_content 命中 +1)."""

    acceptance_count: int = 0
    """应用后用户 approve 的 chapter 数."""

    rejection_count: int = 0
    """应用后用户 reject 的 chapter 数 / regenerate diff 很大 (隐式负反馈)."""

    avg_acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    """acceptance / (acceptance + rejection)."""

    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    """综合分 (cosine × acceptance × recency × usage_confidence), 0-1."""


class SkillDistillSource(BaseModel):
    """Skill 蒸馏来源追溯 (一个 source = 一个 chapter snapshot)."""

    chapter_id: str
    asset_id: str
    asset_version: int = 1
    quoted_at: datetime
    """蒸馏发生的时间 (不是 chapter 当时的 updated_at)."""


class Skill(BaseModel):
    """v0.2 Agent 专家技能 (MVP 项目级私有).

    `skill_md` 是 Anthropic SKILL.md 全文 (YAML frontmatter + 4-6 节正文).
    `embedding` 由后端调 Ollama nomic-embed-text 生成, 用于注入时 cosine top-k 召回.
    """

    id: str
    """skill-{uuid} (生成时分配)."""

    project_id: str
    """MVP 项目级私有 - 不跨项目共享."""

    name: str
    """短名 (slug 风格), e.g. 'pr-summary-formatting'."""

    version: int = 1
    """每次 evolve 递增 (旧版本归档到 deprecated, 新版本 active)."""

    skill_md: str
    """Anthropic SKILL.md 全文 (YAML + 正文). 注入 system_prompt 时直接拼贴."""

    embedding: list[float] | None = None
    """nomic-embed-text 输出 (1024 维默认). None = 待补 embedding."""

    metrics: SkillMetrics = Field(default_factory=SkillMetrics)
    """自进化指标."""

    distilled_from: list[SkillDistillSource] = Field(default_factory=list)
    """来源 chapter 列表 (可追溯;diversity bonus 计算用)."""

    distilled_at: datetime
    """蒸馏完成时刻."""

    last_used_at: datetime | None = None
    """最近一次注入下游生成的时刻 (recency_decay 用)."""

    locked: bool = False
    """True = 不再参与自进化 (人工固化版本); evolve_skill_v2 跳过."""

    status: SkillStatus = "draft"

    parent_skill_id: str | None = None
    """evolve_skill_v2 时记录上一代 skill_id (用于升级历史 timeline)."""

    # ─── v0.5.1 · Q5 contributor 同意闸门 (T48) ────────────────
    contributors: list[str] = Field(default_factory=list)
    """蒸馏来源 chapter 关联到的 contributor user_id 列表.

    distill_skill 时由调用方填入 (从 source_chapters → IMValueSegment.contributors 推导).
    空列表 = 手动蒸馏 / 无 IM 链路, 直接跳过 consent 流程进 draft.
    """

    consent_required_from: list[str] = Field(default_factory=list)
    """需同意的 contributor user_id 列表.

    `initialize_pending(skill)` 时一次性从 `contributors` 复制 (避免事后被改);
    不可手动改 (语义: 锁定签字目标集).
    """

    consent_signed_by: list[ConsentRecord] = Field(default_factory=list)
    """已签字的 contributors. 全员签 (len == len(consent_required_from)) → 转 draft."""

    consent_rejected_by: ConsentRecord | None = None
    """首位拒绝者. 一旦被填则状态冻结到 rejected_by_contributor,
    后续即使其他人签也无效 (单否决原则)."""

    consent_expires_at: datetime | None = None
    """OD-6: initialize_pending 时 +30 天.

    daily sweep_expired_consents 任务扫到 now > consent_expires_at 且仍 pending
    → 转 expired_no_consent.
    """

    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _backfill_consent_fields(cls, values: Any) -> Any:
        """v0.5 之前的 Skill JSON 无 consent 字段; load 时回填 default.

        必须 `mode="before"`: 在 Pydantic 字段默认值填充前注入, 不破坏
        老数据 round-trip (json dump 再 load 不改值).
        """
        if isinstance(values, dict):
            values.setdefault("contributors", [])
            values.setdefault("consent_required_from", [])
            values.setdefault("consent_signed_by", [])
            values.setdefault("consent_rejected_by", None)
            values.setdefault("consent_expires_at", None)
        return values


# ─── 请求 / 响应 DTO ──────────────────────────────────────────────


class SkillDistillRequest(BaseModel):
    """POST /api/v1/projects/:id/skills/distill 请求体."""

    source_chapter_ids: list[str] = Field(..., min_length=1, max_length=10)
    """蒸馏源 chapter (强制 ≥1 且 ≤10, 避免上下文爆炸)."""

    name_hint: str | None = None
    """可选: 用户起的 skill 短名;不提供则 LLM 起名."""


class SkillUpdateRequest(BaseModel):
    """PATCH /api/v1/skills/:id 请求体 (人工编辑 skill_md / 锁定)."""

    skill_md: str | None = None
    name: str | None = None
    locked: bool | None = None
    status: SkillStatus | None = None


class SkillApplicationRecord(BaseModel):
    """Chapter 中记录的 skill 应用 (chapter.applied_skills 单项).

    可直接 dump 到 chapter.applied_skills JSON 数组.
    """

    skill_id: str
    version: int
    applied_at: datetime
    cosine_similarity: float | None = None
    """召回时的 cosine 分数 (调试 / 决策追溯用)."""
