"""ThresholdEvaluator · v0.4.2 (T41).

每 15 分钟由 APScheduler threshold_scanner_job 调度; 评估 mode='threshold' 规则.

支持的 metric (v0.4.2 第一波):
- approved_chapters_total: 项目 chapter.approval_state='approved' 总数 (book 触发)
- events_count_30d: 项目近 30 天 events 数 (备用)

不支持 (v0.4.3+):
- im_signal_count_30d / expert_messages_count / expert_acceptance_rate
  (需要 IM SignalGate 数据, 留与 IM v0.3.2 一起做)

去重保护:
- ThresholdSpec.and_not_exists_asset_of_type: 项目下已有该类型 asset → 跳过
  (e.g. 一项目最多生成一份 book; 避免每 15min 重复触发)
- cooldown_seconds 仍生效 (默认 7 天 for book)
- daily_cap 仍生效

与 cron / event evaluator 区别:
- threshold 是"持续状态"评估, 不像 cron/event 是"瞬时信号"
- 不命中时不写 record_skip (15min 一次, 噪声太多)
- 命中后立即 schedule (走标准 5min 撤回窗口)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.auto_trigger import (
    ThresholdSpec,
    TriggerEvaluation,
    TriggerRule,
    TriggerSignal,
)
from app.services import auto_trigger_service as svc


def _compare(left: float, comparator: str, right: float) -> bool:
    if comparator == ">=":
        return left >= right
    if comparator == "<=":
        return left <= right
    if comparator == "==":
        return left == right
    if comparator == "!=":
        return left != right
    if comparator == ">":
        return left > right
    if comparator == "<":
        return left < right
    raise ValueError(f"未知 comparator: {comparator}")


def _count_approved_chapters(project_id: str) -> int:
    """统计项目下所有 chapter.approval_state='approved' 数量.

    走 generation_service 内存 cache 而非直接 SQL, 避免反复反序列化.
    """
    # 延迟 import 避免循环
    from app.services import generation_service

    n = 0
    for asset in generation_service.list_assets(project_id):
        for c in generation_service.list_chapters(asset.id):
            if c.approval_state == "approved":
                n += 1
    return n


def _count_events_in_window(project_id: str, days: int) -> int:
    """近 N 天 events 数 (复用 store 接口)."""
    since = datetime.now(UTC) - timedelta(days=days)
    return get_db().count_events_in_window(project_id, since.isoformat())


def _has_asset_of_type(project_id: str, asset_type: str) -> bool:
    """项目下是否已存在某类型 asset (除 archived)."""
    from app.services import generation_service

    for a in generation_service.list_assets(project_id):
        if a.type == asset_type and a.status != "archived":
            return True
    return False


def _count_im_signals(project_id: str, days: int) -> int:
    """统计项目下近 N 天 is_signal=1 的 IM 消息数."""
    since = datetime.now(UTC) - timedelta(days=days)
    return get_db().count_im_signals_in_project(project_id, since.isoformat())


def _resolve_metric(
    metric: str, project_id: str, now: datetime
) -> float | None:
    """计算指标当前值. None = 不支持此 metric."""
    if metric == "approved_chapters_total":
        return _count_approved_chapters(project_id)
    if metric == "events_count_30d":
        return _count_events_in_window(project_id, 30)
    if metric == "events_count_7d":
        return _count_events_in_window(project_id, 7)
    # v0.4.2 第二波 (T42) IM signal metrics
    if metric == "im_signal_count_30d":
        return _count_im_signals(project_id, 30)
    if metric == "im_signal_count_7d":
        return _count_im_signals(project_id, 7)
    return None


def _check_threshold(
    spec: ThresholdSpec, project_id: str, now: datetime
) -> tuple[bool, float | None, str | None]:
    """评估单个 threshold; 返回 (passed, actual_value, reason_if_not).

    actual_value 用于 trigger_execution.evaluation 审计.
    """
    actual = _resolve_metric(spec.metric, project_id, now)
    if actual is None:
        return False, None, f"unsupported metric: {spec.metric}"

    if not _compare(actual, spec.comparator, spec.value):
        return False, actual, (
            f"{spec.metric}={actual} {spec.comparator} {spec.value} 不满足"
        )

    # and_not_exists 约束 (Q4 决策: book 一项目一份)
    if spec.and_not_exists_asset_of_type:
        if _has_asset_of_type(project_id, spec.and_not_exists_asset_of_type):
            return False, actual, (
                f"项目已存在 {spec.and_not_exists_asset_of_type} 类型 asset"
            )

    return True, actual, None


def _build_signal(
    rule: TriggerRule, project_id: str, actual: float
) -> TriggerSignal:
    spec = rule.threshold_spec
    summary = (
        f"阈值触发 · {spec.metric}={actual} {spec.comparator} {spec.value}"
        if spec else "阈值触发"
    )
    return TriggerSignal(
        type="threshold_scan",
        event_id=f"threshold:{rule.id}:{project_id}",
        summary=summary,
        payload={
            "rule_id": rule.id,
            "project_id": project_id,
            "metric": spec.metric if spec else "",
            "actual_value": actual,
            "threshold_value": spec.value if spec else 0,
        },
    )


def evaluate_threshold_rules(
    *, withdraw_window_min: float = svc.DEFAULT_WITHDRAW_WINDOW_MIN
) -> dict[str, int]:
    """主入口: 拉所有 enabled mode=threshold 规则 → 对所有 active 项目评估.

    返回评估统计 (供 threshold_scanner_job 写 log).
    """
    rules = svc.list_all_rules(enabled=True, mode="threshold")
    stats = {
        "rules_evaluated": 0,
        "checks": 0,
        "scheduled": 0,
        "skipped_cooldown": 0,
        "skipped_daily_cap": 0,
        "not_satisfied": 0,
        "unsupported_metric": 0,
        "errors": 0,
    }
    if not rules:
        return stats

    db = get_db()
    now = datetime.now(UTC)

    for rule in rules:
        stats["rules_evaluated"] += 1
        if rule.threshold_spec is None:
            logger.warning("auto_trigger_threshold_no_spec", rule_id=rule.id)
            continue

        # fan-out: 实例级规则 → 所有有 events 的项目; 项目级 → 自己
        target_projects = (
            [rule.project_id]
            if rule.project_id is not None
            else db.list_active_project_ids()
        )

        for project_id in target_projects:
            stats["checks"] += 1
            try:
                _evaluate_for_project(
                    rule, project_id, now, withdraw_window_min, stats
                )
            except Exception as e:
                logger.error(
                    "auto_trigger_threshold_evaluate_failed",
                    rule_id=rule.id, project_id=project_id, error=str(e),
                )
                stats["errors"] += 1

    logger.info("auto_trigger_threshold_evaluator_done", **stats)
    return stats


def _evaluate_for_project(
    rule: TriggerRule,
    project_id: str,
    now: datetime,
    withdraw_window_min: float,
    stats: dict[str, int],
) -> None:
    """单 (rule, project): 检查 threshold → cooldown → daily_cap → schedule.

    Threshold 不命中时不写 record_skip (15min 一次, 太多噪声; 仅 log).
    """
    passed, actual, reason = _check_threshold(rule.threshold_spec, project_id, now)
    if not passed:
        if reason and "unsupported" in reason:
            stats["unsupported_metric"] += 1
        else:
            stats["not_satisfied"] += 1
        logger.debug(
            "auto_trigger_threshold_not_passed",
            rule_id=rule.id, project_id=project_id, reason=reason,
        )
        return

    # v0.4.4 · quota throttle (静默跳过, 不写 record_skip 避免 15min 一次的噪声)
    if svc.is_quota_throttled(project_id):
        stats.setdefault("skipped_quota", 0)
        stats["skipped_quota"] += 1
        return

    # cooldown
    if rule.cooldown_seconds > 0:
        since = now - timedelta(seconds=rule.cooldown_seconds)
        if svc.count_fired_since(rule.id, since) > 0:
            stats["skipped_cooldown"] += 1
            return

    # daily_cap
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    if svc.count_fired_since(rule.id, today_start) >= rule.daily_cap:
        stats["skipped_daily_cap"] += 1
        return

    # schedule
    signal = _build_signal(rule, project_id, actual or 0)
    svc.schedule_execution(
        rule, project_id, signal,
        withdraw_window_min=withdraw_window_min,
        evaluation=TriggerEvaluation(
            matched=True, confidence=1.0,
            notes=f"actual={actual} · threshold passed",
        ),
    )
    stats["scheduled"] += 1
    logger.info(
        "auto_trigger_threshold_scheduled",
        rule_id=rule.id, project_id=project_id,
        metric=rule.threshold_spec.metric, actual=actual,
    )


__all__ = ["evaluate_threshold_rules"]
