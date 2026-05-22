"""RuleEvaluator 主流程 (v0.4 T29).

每 1 分钟由 APScheduler cron_evaluator_job 调度:
1. 拉所有 enabled+mode=cron 的规则 (含实例级 + 项目级)
2. 对每条规则:
   a. CronMatcher: 是否在 1 分钟窗口内到点 → 不到则跳过整条
   b. 解析 target_projects: 实例级规则 fan-out 到所有有 events 的项目;
      项目级规则只针对自己的 project_id
   c. 对每个 target_project:
      i.   Cooldown 检查 (最近 fired 时间是否 < cooldown_seconds)
      ii.  DailyCap 检查 (当日 fired 数 < daily_cap)
      iii. ExtraCondition 检查 (events_last_7d >= 30 等)
      iv.  全过 → svc.schedule_execution; 任一失败 → svc.record_skip 写跳过历史

返回评估统计 (供 cron_evaluator_job 写 log).

不在范围:
- mode=event 的事件触发 (v0.4.1 GitHub webhook adapter)
- mode=threshold 的累积扫描 (v0.4.2 threshold_scanner)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.auto_trigger import (
    SkipReason,
    TriggerEvaluation,
    TriggerRule,
    TriggerSignal,
)
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.evaluator.conditions import evaluate_extra_condition
from app.services.auto_trigger.evaluator.cron_matcher import matches_in_window


SCAN_WINDOW_SECONDS = 60
"""与 APScheduler cron_evaluator IntervalTrigger=1min 对齐."""


def _resolve_target_projects(rule: TriggerRule) -> list[str]:
    """规则的目标项目列表.

    - 项目级规则 (rule.project_id 非空): [rule.project_id]
    - 实例级规则 (rule.project_id=None): events 表 distinct project_id
      (没事件的项目无意义触发, 避免空报)
    """
    if rule.project_id is not None:
        return [rule.project_id]
    return get_db().list_active_project_ids()


def _check_cooldown(rule: TriggerRule, project_id: str, now: datetime) -> bool:
    """True = 在 cooldown 内, 应跳过."""
    if rule.cooldown_seconds <= 0:
        return False
    # 查"距 cooldown_seconds 之前 ~ now"窗口内 fired 数量
    since = now - timedelta(seconds=rule.cooldown_seconds)
    n = svc.count_fired_since(rule.id, since)
    return n > 0


def _check_daily_cap(rule: TriggerRule, project_id: str, now: datetime) -> bool:
    """True = 当日 fired 已达上限, 应跳过."""
    # 当天起点 (UTC) → now
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    n = svc.count_fired_since(rule.id, today_start)
    return n >= rule.daily_cap


def _build_signal(rule: TriggerRule, now: datetime) -> TriggerSignal:
    return TriggerSignal(
        type="cron",
        summary=f"{rule.name} · cron 触发 ({now.strftime('%Y-%m-%d %H:%M')})",
        payload={"cron_expr": rule.cron_expr or "", "fire_at_iso": now.isoformat()},
    )


def evaluate_cron_rules(now: datetime | None = None) -> dict[str, int]:
    """评估所有 enabled cron 规则; 返回评估统计.

    Args:
        now: 评估基准时间 (None=now utc); 测试用 freeze_time 注入

    Returns:
        { "evaluated": N, "matched": M, "scheduled": K,
          "skipped_cooldown": ..., "skipped_daily_cap": ...,
          "skipped_extra_condition": ..., "errors": ... }
    """
    if now is None:
        now = datetime.now(timezone.utc)

    stats = {
        "evaluated": 0,
        "matched": 0,
        "scheduled": 0,
        "skipped_cooldown": 0,
        "skipped_daily_cap": 0,
        "skipped_extra_condition": 0,
        "errors": 0,
    }

    # 跨项目拉所有 enabled cron 规则 (实例级 + 全部项目级);
    # T26 list_rules 是 UI 视角的"project 隔离"语义, 此处需要 evaluator 视角的"跨项目"
    rules = svc.list_all_rules(enabled=True, mode="cron")
    for rule in rules:
        stats["evaluated"] += 1
        # 1. CronMatcher: 是否到点
        if not matches_in_window(rule.cron_expr or "", now, SCAN_WINDOW_SECONDS):
            continue
        stats["matched"] += 1

        # 2. fan-out 到目标项目
        try:
            targets = _resolve_target_projects(rule)
        except Exception as e:
            logger.error(
                "auto_trigger_resolve_targets_failed",
                rule_id=rule.id, error=str(e),
            )
            stats["errors"] += 1
            continue

        for project_id in targets:
            try:
                _evaluate_for_project(rule, project_id, now, stats)
            except Exception as e:
                logger.error(
                    "auto_trigger_evaluate_project_failed",
                    rule_id=rule.id, project_id=project_id, error=str(e),
                )
                stats["errors"] += 1

    logger.info(
        "auto_trigger_cron_evaluator_done",
        **stats,
        now=now.isoformat(),
    )
    return stats


def _evaluate_for_project(
    rule: TriggerRule,
    project_id: str,
    now: datetime,
    stats: dict[str, int],
) -> None:
    """单 (rule, project) 评估; 命中 → schedule; 否则 record_skip."""
    signal = _build_signal(rule, now)

    # v0.4.4 · 月配额硬墙: throttled 项目跳过所有触发
    if svc.is_quota_throttled(project_id):
        svc.record_skip(
            rule, project_id, signal, "quota_exceeded",
            evaluation=TriggerEvaluation(matched=True, confidence=1.0,
                                          notes="项目月配额已耗尽"),
        )
        stats.setdefault("skipped_quota", 0)
        stats["skipped_quota"] += 1
        return

    # 3a. cooldown
    if _check_cooldown(rule, project_id, now):
        svc.record_skip(
            rule, project_id, signal, "cooldown",
            evaluation=TriggerEvaluation(matched=True, confidence=1.0,
                                          notes=f"距上次 fired < {rule.cooldown_seconds}s"),
        )
        stats["skipped_cooldown"] += 1
        return

    # 3b. daily_cap
    if _check_daily_cap(rule, project_id, now):
        svc.record_skip(
            rule, project_id, signal, "daily_cap_reached",
            evaluation=TriggerEvaluation(matched=True, confidence=1.0,
                                          notes=f"当日 fired ≥ {rule.daily_cap}"),
        )
        stats["skipped_daily_cap"] += 1
        return

    # 3c. extra_condition
    passed, actual = evaluate_extra_condition(rule.extra_condition, project_id, now=now)
    if not passed:
        notes = (
            f"{rule.extra_condition.metric} = {actual} "
            f"{rule.extra_condition.comparator} {rule.extra_condition.value} 不满足"
            if rule.extra_condition is not None
            else ""
        )
        svc.record_skip(
            rule, project_id, signal, "extra_condition_failed",
            evaluation=TriggerEvaluation(
                matched=True, confidence=1.0,
                extra_condition_result=False, notes=notes,
            ),
        )
        stats["skipped_extra_condition"] += 1
        return

    # 4. 全过 → schedule (5 分钟撤回窗口)
    svc.schedule_execution(
        rule, project_id, signal,
        evaluation=TriggerEvaluation(
            matched=True, confidence=1.0,
            extra_condition_result=passed if rule.extra_condition else None,
            notes=f"actual_metric={actual}" if actual is not None else None,
        ),
    )
    stats["scheduled"] += 1


__all__ = ["evaluate_cron_rules", "SCAN_WINDOW_SECONDS"]
