"""ExtraCondition / ThresholdSpec 指标评估 (v0.4 T29).

支持的 metric (v0.4.0):
- events_last_7d: 项目 events 表近 7 天事件数
- events_last_30d: 项目近 30 天事件数

不支持 (留 v0.4.2):
- approved_chapters_total / im_signal_count_30d 等 threshold 专属指标
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.auto_trigger import ExtraCondition


def _compare(left: float, comparator: str, right: float) -> bool:
    """6 种比较运算符."""
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


def _resolve_metric(metric: str, project_id: str, now: datetime) -> float | None:
    """计算指标当前值. None = 不支持此 metric."""
    db = get_db()
    if metric == "events_last_7d":
        since = now - timedelta(days=7)
        return db.count_events_in_window(project_id, since.isoformat())
    if metric == "events_last_30d":
        since = now - timedelta(days=30)
        return db.count_events_in_window(project_id, since.isoformat())
    # v0.4.0 不支持的 metric → 返回 None
    return None


def evaluate_extra_condition(
    cond: ExtraCondition | None,
    project_id: str,
    now: datetime | None = None,
) -> tuple[bool, float | None]:
    """评估 extra_condition. cond=None → 视为通过 (无附加要求).

    Returns:
        (passed, actual_value):
          - passed: 条件是否满足
          - actual_value: 当前指标值 (用于审计 / log; metric 不支持时 None)
    """
    if cond is None:
        return True, None
    if now is None:
        now = datetime.now(timezone.utc)

    actual = _resolve_metric(cond.metric, project_id, now)
    if actual is None:
        logger.warning(
            "auto_trigger_metric_unsupported",
            metric=cond.metric,
            project_id=project_id,
        )
        # 不支持的 metric 视为"通过" (不阻塞触发); 由 caller 通过 log 感知
        return True, None
    passed = _compare(actual, cond.comparator, cond.value)
    return passed, actual


__all__ = ["evaluate_extra_condition"]
