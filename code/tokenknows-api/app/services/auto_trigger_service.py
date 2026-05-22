"""Auto-Trigger 业务服务 (v0.4 T26).

职责:
- TriggerRule CRUD (id / 时间戳生成, Pydantic dump, mode/spec 配对校验)
- TriggerExecution 生命周期 (schedule / fire / cancel / skip / expire) + 状态机校验
- 启动时回填内存 (load_all_*)
- GenerationQuota 占位 CRUD (v0.4.0 不做配额检查, 仅建表/读写)

不在范围:
- 规则评估循环 (T29 cron_evaluator / RuleEvaluator)
- dispatcher fire 逻辑 (T30, 由本服务的 update_execution 提供原子转换原语)
- withdraw_resolver 循环 (T31)
- REST API (T32)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.auto_trigger import (
    ExecutionStatus,
    GenerationQuota,
    SkipReason,
    TriggerExecution,
    TriggerMode,
    TriggerRule,
    TriggerSignal,
    can_transition,
)


# ─── 常量 ──────────────────────────────────────────────────

DEFAULT_WITHDRAW_WINDOW_MIN = 5
"""默认撤回窗口长度 (Q1 决策: 用户可调 1-15 min, 默认 5)."""

EXPIRED_GRACE_MIN = 60
"""scheduled 但 fire_at 过去 > 60 min 仍未被 dispatcher 处理 → 标 expired."""


# ─── 工具 ──────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ─── 异常 ──────────────────────────────────────────────────


class AutoTriggerError(Exception):
    """业务异常基类."""


class RuleSpecMismatch(AutoTriggerError):
    """规则的 mode 与 spec 字段不匹配 (如 mode=cron 但没有 cron_expr)."""


class InvalidTransition(AutoTriggerError):
    """非法状态机转换 (如 fired → canceled)."""


class ExecutionNotFound(AutoTriggerError):
    pass


class RuleNotFound(AutoTriggerError):
    pass


# ─── Rule CRUD ────────────────────────────────────────────


def _validate_rule_spec(rule: TriggerRule) -> None:
    """mode 与 spec 字段配对校验. 创建/更新前调用."""
    if rule.mode == "cron":
        if not rule.cron_expr:
            raise RuleSpecMismatch("mode=cron 必须填 cron_expr")
        # 不强校验 cron 语法 (留给 RuleEvaluator T29 的 croniter)
    elif rule.mode == "event":
        if rule.event_match is None:
            raise RuleSpecMismatch("mode=event 必须填 event_match")
    elif rule.mode == "threshold":
        if rule.threshold_spec is None:
            raise RuleSpecMismatch("mode=threshold 必须填 threshold_spec")
    elif rule.mode == "mention":
        # v0.4.3 / v0.3.4 复用; 本版本不强校验
        pass


def create_rule(
    *,
    project_id: str | None,
    name: str,
    mode: TriggerMode,
    asset_type: str,
    created_by: str,
    description: str = "",
    priority: int = 50,
    enabled: bool = True,
    cooldown_seconds: int = 3600,
    daily_cap: int = 5,
    cron_expr: str | None = None,
    event_match: Any = None,
    threshold_spec: Any = None,
    extra_condition: Any = None,
    config: dict[str, Any] | None = None,
) -> TriggerRule:
    now = _now()
    rule = TriggerRule(
        id=_new_id("rule"),
        project_id=project_id,
        name=name,
        description=description,
        priority=priority,
        mode=mode,
        asset_type=asset_type,
        enabled=enabled,
        cooldown_seconds=cooldown_seconds,
        daily_cap=daily_cap,
        cron_expr=cron_expr,
        event_match=event_match,
        threshold_spec=threshold_spec,
        extra_condition=extra_condition,
        created_by=created_by,
        config=config or {},
        created_at=now,
        updated_at=now,
    )
    _validate_rule_spec(rule)

    db = get_db()
    db.upsert_trigger_rule(
        rule_id=rule.id,
        project_id=rule.project_id,
        name=rule.name,
        mode=rule.mode,
        asset_type=rule.asset_type,
        enabled=rule.enabled,
        priority=rule.priority,
        updated_at=_to_iso(rule.updated_at),
        json_str=rule.model_dump_json(),
    )
    logger.info(
        "auto_trigger_rule_created",
        rule_id=rule.id,
        project_id=rule.project_id,
        mode=rule.mode,
        asset_type=rule.asset_type,
    )
    return rule


def get_rule(rule_id: str) -> TriggerRule | None:
    raw = get_db().get_trigger_rule(rule_id)
    if raw is None:
        return None
    return TriggerRule.model_validate(raw)


def list_rules(
    project_id: str | None = None,
    enabled: bool | None = None,
    mode: TriggerMode | None = None,
    include_instance_defaults: bool = True,
) -> list[TriggerRule]:
    raws = get_db().list_trigger_rules(
        project_id=project_id,
        enabled=enabled,
        mode=mode,
        include_instance_defaults=include_instance_defaults,
    )
    return [TriggerRule.model_validate(r) for r in raws]


def list_all_rules(
    enabled: bool | None = None,
    mode: TriggerMode | None = None,
) -> list[TriggerRule]:
    """跨项目拉所有规则 (含实例级 + 全部项目级).

    T29 RuleEvaluator 调用入口; UI 列表 / seeder 用 list_rules (有 project 隔离).
    """
    raws = get_db().list_all_trigger_rules(enabled=enabled, mode=mode)
    return [TriggerRule.model_validate(r) for r in raws]


def update_rule(rule_id: str, **changes: Any) -> TriggerRule:
    """部分更新 (UI 主要用于启停 + 改 priority/cooldown)."""
    current = get_rule(rule_id)
    if current is None:
        raise RuleNotFound(rule_id)

    updated_dict = current.model_dump()
    for k, v in changes.items():
        if k in {"id", "created_at", "created_by"}:
            continue  # 这些字段不可改
        updated_dict[k] = v
    updated_dict["updated_at"] = _now()

    updated = TriggerRule.model_validate(updated_dict)
    _validate_rule_spec(updated)

    get_db().upsert_trigger_rule(
        rule_id=updated.id,
        project_id=updated.project_id,
        name=updated.name,
        mode=updated.mode,
        asset_type=updated.asset_type,
        enabled=updated.enabled,
        priority=updated.priority,
        updated_at=_to_iso(updated.updated_at),
        json_str=updated.model_dump_json(),
    )
    logger.info(
        "auto_trigger_rule_updated",
        rule_id=updated.id,
        changes=list(changes.keys()),
    )
    return updated


def delete_rule(rule_id: str) -> bool:
    """级联删除 (trigger_executions 同步 CASCADE)."""
    ok = get_db().delete_trigger_rule(rule_id)
    if ok:
        logger.info("auto_trigger_rule_deleted", rule_id=rule_id)
    return ok


# ─── Execution lifecycle ──────────────────────────────────


def schedule_execution(
    rule: TriggerRule,
    project_id: str,
    signal: TriggerSignal,
    *,
    withdraw_window_min: float = DEFAULT_WITHDRAW_WINDOW_MIN,
    evaluation: Any = None,
) -> TriggerExecution:
    """规则命中后调用, 写一条 status=scheduled 的执行记录.

    fire_at = now + withdraw_window_min (Q1: 默认 5 min, 1-15 min 可调).
    """
    now = _now()
    fire_at = now + timedelta(minutes=withdraw_window_min)

    execution = TriggerExecution(
        id=_new_id("exec"),
        rule_id=rule.id,
        project_id=project_id,
        status="scheduled",
        fire_at=fire_at,
        fired_at=None,
        signal=signal,
        evaluation=evaluation,
        asset_id=None,
        skip_reason=None,
        error_message=None,
        user_canceled=False,
        user_flagged_false_positive=False,
        created_at=now,
    )
    get_db().insert_trigger_execution(
        execution_id=execution.id,
        rule_id=execution.rule_id,
        project_id=execution.project_id,
        status=execution.status,
        fire_at=_to_iso(execution.fire_at),
        fired_at=None,
        asset_id=None,
        created_at=_to_iso(execution.created_at),
        json_str=execution.model_dump_json(),
    )
    logger.info(
        "auto_trigger_scheduled",
        execution_id=execution.id,
        rule_id=rule.id,
        fire_at=_to_iso(fire_at),
    )
    return execution


def record_skip(
    rule: TriggerRule,
    project_id: str,
    signal: TriggerSignal,
    skip_reason: SkipReason,
    *,
    evaluation: Any = None,
) -> TriggerExecution:
    """规则评估时被跳过 (cooldown / daily_cap / extra_condition_failed 等).

    写一条 status=skipped 的执行记录, 不进入撤回窗口.
    """
    now = _now()
    execution = TriggerExecution(
        id=_new_id("exec"),
        rule_id=rule.id,
        project_id=project_id,
        status="skipped",
        fire_at=now,
        fired_at=None,
        signal=signal,
        evaluation=evaluation,
        asset_id=None,
        skip_reason=skip_reason,
        error_message=None,
        user_canceled=False,
        user_flagged_false_positive=False,
        created_at=now,
    )
    get_db().insert_trigger_execution(
        execution_id=execution.id,
        rule_id=execution.rule_id,
        project_id=execution.project_id,
        status=execution.status,
        fire_at=_to_iso(execution.fire_at),
        fired_at=None,
        asset_id=None,
        created_at=_to_iso(execution.created_at),
        json_str=execution.model_dump_json(),
    )
    logger.info(
        "auto_trigger_skipped",
        execution_id=execution.id,
        rule_id=rule.id,
        reason=skip_reason,
    )
    return execution


def get_execution(execution_id: str) -> TriggerExecution | None:
    raw = get_db().get_trigger_execution(execution_id)
    if raw is None:
        return None
    return TriggerExecution.model_validate(raw)


def _transition(
    execution_id: str,
    to_status: ExecutionStatus,
    *,
    asset_id: str | None = None,
    error_message: str | None = None,
    user_canceled: bool = False,
) -> TriggerExecution:
    """通用状态机转换. 内部使用; 公开 API 用具体方法 (fire / cancel / mark_failed / mark_expired)."""
    current = get_execution(execution_id)
    if current is None:
        raise ExecutionNotFound(execution_id)
    if not can_transition(current.status, to_status):
        raise InvalidTransition(
            f"非法转换: {current.status} → {to_status} (execution={execution_id})"
        )

    updated_dict = current.model_dump()
    updated_dict["status"] = to_status
    if to_status == "fired":
        updated_dict["fired_at"] = _now()
        updated_dict["asset_id"] = asset_id
    if error_message:
        updated_dict["error_message"] = error_message
    if user_canceled:
        updated_dict["user_canceled"] = True

    updated = TriggerExecution.model_validate(updated_dict)
    ok = get_db().update_trigger_execution(
        execution_id=updated.id,
        status=updated.status,
        fired_at=_to_iso(updated.fired_at) if updated.fired_at else None,
        asset_id=updated.asset_id,
        json_str=updated.model_dump_json(),
    )
    if not ok:
        raise ExecutionNotFound(execution_id)
    logger.info(
        "auto_trigger_transition",
        execution_id=updated.id,
        from_status=current.status,
        to_status=to_status,
        asset_id=asset_id,
    )
    return updated


def mark_fired(execution_id: str, asset_id: str) -> TriggerExecution:
    """T30 dispatcher 成功调 LLM 后调用."""
    return _transition(execution_id, "fired", asset_id=asset_id)


def cancel_execution(execution_id: str, *, by_user: bool = True) -> TriggerExecution:
    """用户撤回窗口期内点取消; 仅 scheduled → canceled 合法."""
    return _transition(execution_id, "canceled", user_canceled=by_user)


def mark_failed(execution_id: str, error: str) -> TriggerExecution:
    return _transition(execution_id, "failed", error_message=error)


def mark_expired(execution_id: str) -> TriggerExecution:
    """T31 兜底: fire_at 过期 > grace_min 仍未被 fire."""
    return _transition(execution_id, "expired", error_message="dispatcher 超时未处理")


def flag_false_positive(execution_id: str) -> TriggerExecution:
    """用户报告误触发. 不改 status (可能已是 fired/canceled), 只标 flag."""
    current = get_execution(execution_id)
    if current is None:
        raise ExecutionNotFound(execution_id)
    updated_dict = current.model_dump()
    updated_dict["user_flagged_false_positive"] = True
    updated = TriggerExecution.model_validate(updated_dict)
    get_db().update_trigger_execution(
        execution_id=updated.id,
        status=updated.status,
        fired_at=_to_iso(updated.fired_at) if updated.fired_at else None,
        asset_id=updated.asset_id,
        json_str=updated.model_dump_json(),
    )
    logger.info("auto_trigger_false_positive_flagged", execution_id=updated.id)
    return updated


def list_executions(
    project_id: str | None = None,
    rule_id: str | None = None,
    status: ExecutionStatus | None = None,
    limit: int = 50,
) -> list[TriggerExecution]:
    raws = get_db().list_trigger_executions(
        project_id=project_id,
        rule_id=rule_id,
        status=status,
        limit=limit,
    )
    return [TriggerExecution.model_validate(r) for r in raws]


def list_ready_to_fire(limit: int = 100) -> list[TriggerExecution]:
    """T31 withdraw_window_resolver 主调入口: 拉所有 fire_at 已过的 scheduled 执行."""
    raws = get_db().list_scheduled_executions_ready(
        now_iso=_to_iso(_now()), limit=limit
    )
    return [TriggerExecution.model_validate(r) for r in raws]


def count_fired_since(rule_id: str, since: datetime) -> int:
    """RuleEvaluator (T29) 用于 cooldown / daily_cap 校验."""
    return get_db().count_fired_in_window(rule_id, _to_iso(since))


def sweep_expired(grace_min: int = EXPIRED_GRACE_MIN) -> int:
    """T31 兜底扫描: scheduled 但 fire_at 过去 > grace_min 的 → 标 expired.

    返回处理条数.
    """
    cutoff = _now() - timedelta(minutes=grace_min)
    raws = get_db().list_scheduled_executions_ready(
        now_iso=_to_iso(cutoff), limit=1000
    )
    n = 0
    for raw in raws:
        try:
            mark_expired(raw["id"])
            n += 1
        except (ExecutionNotFound, InvalidTransition):
            # 已被别处转走; 忽略.
            pass
    if n > 0:
        logger.info("auto_trigger_sweep_expired", count=n)
    return n


# ─── Quota (v0.4.0 占位; v0.4.4 才用) ─────────────────────


def get_or_create_quota(
    project_id: str,
    year_month: str | None = None,
    *,
    monthly_token_limit: int = 5_000_000,
    daily_auto_gen_limit: int = 20,
) -> GenerationQuota:
    """读取项目本月 quota; 不存在则按默认值创建.

    year_month=None → 用 utc now 的 'YYYY-MM'.
    """
    if year_month is None:
        year_month = _now().strftime("%Y-%m")
    raw = get_db().get_quota(project_id, year_month)
    if raw is not None:
        return GenerationQuota.model_validate(raw)

    now = _now()
    quota = GenerationQuota(
        id=_new_id("quota"),
        project_id=project_id,
        year_month=year_month,
        monthly_token_limit=monthly_token_limit,
        daily_auto_gen_limit=daily_auto_gen_limit,
        tokens_used=0,
        auto_gen_count=0,
        is_throttled=False,
        throttled_at=None,
        created_at=now,
        updated_at=now,
    )
    get_db().upsert_quota(
        quota_id=quota.id,
        project_id=quota.project_id,
        year_month=quota.year_month,
        monthly_token_limit=quota.monthly_token_limit,
        daily_auto_gen_limit=quota.daily_auto_gen_limit,
        tokens_used=quota.tokens_used,
        auto_gen_count=quota.auto_gen_count,
        is_throttled=quota.is_throttled,
        updated_at=_to_iso(quota.updated_at),
        json_str=quota.model_dump_json(),
    )
    return quota


# ─── 启动回填 (lifespan startup hook) ─────────────────────


def bootstrap() -> dict[str, int]:
    """main.py lifespan 启动时调; 记录已存在规则/执行数到 log.

    不在此处 seed 默认规则 (T28 seeder 独立任务).
    """
    rules = get_db().load_all_trigger_rules()
    executions = get_db().load_all_trigger_executions(limit=1000)
    scheduled_n = sum(1 for e in executions if e.get("status") == "scheduled")
    logger.info(
        "auto_trigger_bootstrapped",
        rules=len(rules),
        executions_total=len(executions),
        scheduled_pending=scheduled_n,
    )
    return {
        "rules": len(rules),
        "executions": len(executions),
        "scheduled_pending": scheduled_n,
    }
