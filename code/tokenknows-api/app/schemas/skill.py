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


# ─── v0.6.0 · Reviewer 审批流 (T56) ───────────────────────────────


ReviewState = Literal[
    "not_submitted",   # 默认 (draft 但尚未提交审批)
    "pending_review",  # submit_for_review 后, 等 reviewer 处理
    "approved",        # reviewer 批准 → status 同步转 active
    "rejected",        # reviewer 拒绝 → 保留 draft, 作者可修改后再提交
]


class ReviewRecord(BaseModel):
    """单次审批结果 (approve / reject 都用同一类型).

    Skill.review_history 是 list[ReviewRecord] (按时间顺序); 当前状态由
    review_state 字段表达, 历史用于审计追溯.
    """

    reviewer_id: str
    """审批者 user_id (MVP 由 endpoint body 传入; 生产换 session 解出)."""

    action: Literal["submit", "approve", "reject"]
    """submit = 作者提交; approve / reject = reviewer 决定."""

    timestamp: datetime
    """决定时刻 (UTC)."""

    note: str | None = None
    """reject 时必填 (≥ 1 字, 由 endpoint Pydantic 校验)."""


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

    # ─── v0.6.0 · Reviewer 审批流 (T56) ────────────────────────
    review_state: ReviewState = "not_submitted"
    """审批阶段状态. 与 status 正交 (e.g. draft + pending_review).

    转换矩阵:
    not_submitted → pending_review (submit_for_review)
    pending_review → approved (reviewer approve, 同时 status: draft→active)
    pending_review → rejected (reviewer reject)
    rejected → pending_review (作者修改后重提)
    approved → 终态 (不可改; 想改先 status: active→draft 走新 cycle)
    """

    review_history: list[ReviewRecord] = Field(default_factory=list)
    """审批轨迹 (submit / approve / reject 都 append).

    按时间顺序; UI 展示 reviewer timeline. 最新一项 = 当前 review_state 来源.
    """

    last_reviewer_id: str | None = None
    """最近一次 approve / reject 的 reviewer (UI badge / 通知路由方便)."""

    last_reviewed_at: datetime | None = None
    """最近一次 approve / reject 的时刻."""

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
            # v0.5 consent (T48)
            values.setdefault("contributors", [])
            values.setdefault("consent_required_from", [])
            values.setdefault("consent_signed_by", [])
            values.setdefault("consent_rejected_by", None)
            values.setdefault("consent_expires_at", None)
            # v0.6 review (T56)
            values.setdefault("review_state", "not_submitted")
            values.setdefault("review_history", [])
            values.setdefault("last_reviewer_id", None)
            values.setdefault("last_reviewed_at", None)
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


# ─── v0.5.1 · Consent Sign/Reject (T50) ───────────────────────────


class ConsentSignRequest(BaseModel):
    """POST /api/v1/skills/:id/consent/sign body."""

    user_id: str = Field(..., min_length=1, max_length=128)
    """签字者 user_id (从 IM 链接或 web 登录态获取).

    MVP 阶段无完整 SSO, endpoint 接收 user_id 作为 trust-on-faith;
    生产应换为 session 解出, 这里仅传入便于测试 + 写审计.
    """
    channel: Literal["im_dm", "web"] = "web"
    note: str | None = Field(default=None, max_length=200)


class ConsentRejectRequest(BaseModel):
    """POST /api/v1/skills/:id/consent/reject body."""

    user_id: str = Field(..., min_length=1, max_length=128)
    channel: Literal["im_dm", "web"] = "web"
    reason: str = Field(..., min_length=1, max_length=500)
    """必填; 用于审计 + SignalGate 调权."""


class ConsentSignResponse(BaseModel):
    skill_id: str
    current_status: SkillStatus
    signed_count: int
    required_count: int
    all_signed: bool


class ConsentRejectResponse(BaseModel):
    skill_id: str
    current_status: SkillStatus
    rejected_by: str


# ─── v0.6.0 · Reviewer 审批 endpoints (T57) ─────────────────────


class SkillSubmitForReviewRequest(BaseModel):
    """POST /skills/:id/submit-for-review body.

    作者主动提交; user_id 是当前 contributor 之一 (或 project owner).
    """

    user_id: str = Field(..., min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=300)
    """可选: 给 reviewer 的说明."""


class SkillReviewApproveRequest(BaseModel):
    """POST /skills/:id/review/approve body."""

    reviewer_id: str = Field(..., min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=300)


class SkillReviewRejectRequest(BaseModel):
    """POST /skills/:id/review/reject body. reason 必填."""

    reviewer_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(..., min_length=1, max_length=500)


class SkillReviewActionResponse(BaseModel):
    """3 endpoint 公用响应."""

    skill_id: str
    status: SkillStatus
    review_state: ReviewState
    last_action: Literal["submit", "approve", "reject"]
    last_reviewer_id: str | None = None
    last_reviewed_at: datetime | None = None


class SkillApplicationRecord(BaseModel):
    """Chapter 中记录的 skill 应用 (chapter.applied_skills 单项).

    可直接 dump 到 chapter.applied_skills JSON 数组.
    """

    skill_id: str
    version: int
    applied_at: datetime
    cosine_similarity: float | None = None
    """召回时的 cosine 分数 (调试 / 决策追溯用)."""
