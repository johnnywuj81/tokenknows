"""Auto-Trigger DTO · v0.4 起步 (T26).

来源:
- Proposal_Automatic_Generation_Trigger_v0.4.md §8 数据模型
- engineering_handoff/tasks/T26-auto-trigger-db-schema.md

设计偏差 (MVP SQLite vs Proposal PG):
- 无 alembic / migrations 框架, schema.sql 由 store.py bootstrap 时 CREATE TABLE IF NOT EXISTS
- JSONB 字段改 TEXT 存 JSON 字符串 (signal / evaluation / event_match / threshold_spec)
- 无 SELECT FOR UPDATE SKIP LOCKED (v0.4 单实例 OK; v0.5 多实例时迁 PG)
- UNIQUE NULLS NOT DISTINCT 用 partial unique index 模拟 (project_id IS NULL 单独 unique)
- generation_quota 仅 v0.4.4 真正激活, T26 只建表 + 占位字段
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ─── 类型定义 ────────────────────────────────────────────────

TriggerMode = Literal["cron", "event", "threshold", "mention"]
"""5 种触发模式: M2 cron / M3 event / M4 threshold / M5 @机器人.
M1 手动不入 trigger_rule 表 (手动是 UI 直接调 generate, 不经规则引擎)."""

ExecutionStatus = Literal[
    "scheduled",  # 命中规则, 等待 5 分钟撤回窗口
    "fired",      # 撤回窗口已过, LLM 已调用, asset 已生成
    "canceled",   # 用户在撤回窗口内取消
    "skipped",    # cooldown / daily_cap / extra_condition 未满足
    "failed",     # LLM 调用失败 / generation pipeline 抛错
    "expired",    # status=scheduled 但 fire_at 已过 1h 仍未被 dispatcher 处理 (兜底)
]

SkipReason = Literal[
    "cooldown",                # 距上次 fire 不足 cooldown_seconds
    "daily_cap_reached",       # 当日同类型已达上限
    "extra_condition_failed",  # extra_condition 表达式不满足 (如 events_last_7d < 30)
    "rule_disabled",           # 评估时被禁用
    "lower_priority",          # 同时被更高优先级规则命中
    "low_confidence",          # LLM fallback 路由置信度 < 阈值
    "quota_exceeded",          # 项目月配额已耗尽
    "canceled_by_user",        # 用户在撤回窗口内取消 (实际写 status=canceled, 此处为兼容)
]


# ─── 嵌入对象 ────────────────────────────────────────────────


class EventMatch(BaseModel):
    """mode=event 规则的匹配条件 (Proposal 附录 A.2/A.3 风格)."""

    event_type: str
    """事件类型, e.g. 'github_pr_merged' / 'github_issue_opened' / 'im_signal_burst'."""

    label_any: list[str] = Field(default_factory=list)
    """labels 命中任一即匹配; 空列表 = 不校验 labels."""

    file_glob: list[str] = Field(default_factory=list)
    """files changed 匹配任一 glob (仅 PR 事件); 空列表 = 不校验文件."""

    title_contains: list[str] = Field(default_factory=list)
    """PR/Issue title 含任一字符串即匹配 (大小写不敏感); 空列表 = 不校验."""

    extra: dict[str, Any] = Field(default_factory=dict)
    """v0.4.1+ 扩展字段; 当前未使用."""


class ThresholdSpec(BaseModel):
    """mode=threshold 规则的阈值条件 (Proposal 附录 A.4 风格)."""

    metric: str
    """指标名, e.g. 'approved_chapters_total' / 'im_signal_count_30d' /
    'events_last_7d' / 'expert_messages_count' / 'expert_acceptance_rate'."""

    comparator: Literal[">=", "<=", "==", "!=", ">", "<"]

    value: float
    """阈值数值."""

    and_not_exists_asset_of_type: str | None = None
    """额外约束: 仅当项目下不存在该类型 asset 时才触发 (如 book 只生成一次)."""

    extra: dict[str, Any] = Field(default_factory=dict)


class ExtraCondition(BaseModel):
    """规则触发的附加条件 (适用于 mode=cron / event); 不满足 → status=skipped.

    e.g. 周一 09:00 cron 触发周报, 但要求"上周事件 ≥ 30"才真触发, 否则当周无内容跳过.
    """

    metric: str
    comparator: Literal[">=", "<=", "==", "!=", ">", "<"]
    value: float


class TriggerSignal(BaseModel):
    """trigger_execution.signal 的结构化 payload (Proposal §7.2 AT-B.1)."""

    type: str
    """信号源类型, e.g. 'cron' / 'github_webhook' / 'im_threshold' / 'manual_mention'."""

    event_id: str | None = None
    """关联事件 id (e.g. 'pr_merged_1234' / im_message id), 用于反查."""

    summary: str
    """人类可读摘要, 显示在 UI 可解释卡上.
    e.g. 'PR #1234 merged with label architecture-decision' / '周一 09:00 定时触发'."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """完整信号 payload (e.g. GitHub webhook body 摘要), 用于审计."""


class TriggerEvaluation(BaseModel):
    """规则评估过程的快照 (写入 trigger_execution.evaluation)."""

    matched: bool
    confidence: float = 1.0
    """规则路由置信度: 规则命中 = 1.0; LLM fallback 时 < 1.0."""

    dropped_rules: list[str] = Field(default_factory=list)
    """同时被命中但优先级更低、被丢弃的 rule_id 列表."""

    extra_condition_result: bool | None = None
    """extra_condition 评估结果 (None = 不适用)."""

    notes: str | None = None


# ─── 主表 ────────────────────────────────────────────────────


class TriggerRule(BaseModel):
    """单条自动触发规则 (Proposal §8.1)."""

    id: str
    project_id: str | None = None
    """实例级默认规则 = None; 项目自定义规则 = 具体 project_id."""

    name: str
    description: str = ""
    priority: int = Field(default=50, ge=0, le=100)
    """0-100, 数值越大越优先; 同时命中只取最高."""

    mode: TriggerMode
    asset_type: str
    """命中后生成的 asset 类型, e.g. 'weekly_report' / 'adr' / 'incident' / 'book' / 'agent_skill'."""

    enabled: bool = True

    cooldown_seconds: int = Field(default=3600, ge=60)
    """同规则相邻 fire 至少间隔 (秒). 最小 60 防风暴."""

    daily_cap: int = Field(default=5, ge=1, le=100)
    """同类型每日上限."""

    # 各 mode 专属配置 (互斥; 仅对应 mode 时填)
    cron_expr: str | None = None
    """mode='cron' 时必填. 5 段 cron, timezone='Asia/Shanghai'."""

    event_match: EventMatch | None = None
    """mode='event' 时必填."""

    threshold_spec: ThresholdSpec | None = None
    """mode='threshold' 时必填."""

    extra_condition: ExtraCondition | None = None
    """cron / event 模式的额外门槛 (可选)."""

    created_by: str
    """创建者 user_id; 实例级规则 = 'system'."""

    config: dict[str, Any] = Field(default_factory=dict)
    """扩展配置 (e.g. UI builder 的元数据)."""

    created_at: datetime
    updated_at: datetime

    @field_validator("cron_expr")
    @classmethod
    def _validate_cron_expr_with_mode(cls, v: str | None, info: Any) -> str | None:
        # 不在此处强校验 mode 关联 (Pydantic v2 field_validator 拿不到 model_data).
        # 由 service 层 / store 层在 upsert 前校验 mode/spec 配对.
        return v


class TriggerExecution(BaseModel):
    """单次规则评估执行记录 (Proposal §8.2)."""

    id: str
    rule_id: str
    project_id: str
    """规则可能是实例级 (project_id=None), 但执行总是落到具体项目."""

    status: ExecutionStatus

    fire_at: datetime
    """计划触发时间. 默认 = created_at + 5min 撤回窗口."""

    fired_at: datetime | None = None
    """实际触发完成时间 (status 进入 fired 时填)."""

    signal: TriggerSignal
    evaluation: TriggerEvaluation | None = None

    asset_id: str | None = None
    """status=fired 时关联生成的 asset id."""

    skip_reason: SkipReason | None = None
    error_message: str | None = None

    user_canceled: bool = False
    """status=canceled 时为 True; 显式记录是否人工取消 (vs 系统 expired)."""

    user_flagged_false_positive: bool = False
    """误触发反馈 (Proposal §7.5 / 体验要素 #34)."""

    created_at: datetime


class GenerationQuota(BaseModel):
    """项目月 LLM token 配额 (Proposal §8.3).

    v0.4.0 仅建表 + 占位字段, T26 不实现完整配额逻辑 (v0.4.4 才接入).
    """

    id: str
    project_id: str
    year_month: str
    """格式 'YYYY-MM' (e.g. '2026-05')."""

    monthly_token_limit: int = Field(default=5_000_000, ge=0)
    """月 token 上限 (Q3 决策: 默认 5M)."""

    daily_auto_gen_limit: int = Field(default=20, ge=1, le=200)
    """每日自动生成数量上限."""

    tokens_used: int = 0
    auto_gen_count: int = 0

    is_throttled: bool = False
    """超额自动 throttle; 当月所有 enabled rule 跳过."""

    throttled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─── Asset patch (v0.4: asset.trigger_meta) ────────────────


class AssetTriggerMeta(BaseModel):
    """挂在 Asset 上, 表示该 asset 由 v0.4 自动触发生成 (Proposal §7.2 AT-B.1).

    手动生成的 asset → trigger_meta=None; v0.4 自动生成的 → 完整填写.
    用于:
    1. UI 显示 "🤖 自动触发" 徽标 (体验要素 #33)
    2. 可解释卡 (体验要素 #34): "为什么被生成 / 为什么是这个类型"
    3. 审计回溯
    """

    trigger_mode: TriggerMode
    rule_id: str
    rule_name: str
    signal: TriggerSignal
    confidence: float = 1.0
    fired_at: datetime
    trigger_execution_id: str | None = None
    """反查 trigger_execution 详情. 早期 v0.4.0 可能未关联, 用 Optional."""


# ─── 状态机辅助 ────────────────────────────────────────────


_ALLOWED_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    "scheduled": {"fired", "canceled", "skipped", "failed", "expired"},
    "fired": set(),       # terminal
    "canceled": set(),    # terminal
    "skipped": set(),     # terminal
    "failed": set(),      # terminal
    "expired": set(),     # terminal
}


def can_transition(
    from_status: ExecutionStatus, to_status: ExecutionStatus
) -> bool:
    """校验状态机合法转换. dispatcher / cancel API 用."""
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, set())


__all__ = [
    "TriggerMode",
    "ExecutionStatus",
    "SkipReason",
    "EventMatch",
    "ThresholdSpec",
    "ExtraCondition",
    "TriggerSignal",
    "TriggerEvaluation",
    "TriggerRule",
    "TriggerExecution",
    "GenerationQuota",
    "AssetTriggerMeta",
    "can_transition",
]
