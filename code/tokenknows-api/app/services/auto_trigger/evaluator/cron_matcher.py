"""Cron 表达式匹配器 (v0.4 T29).

核心问题: 给定 cron_expr 和当前时间, 判断它"是否在最近 N 秒内到点".

实现思路:
- 用 croniter 计算 cron 的"上一次触发时间" prev_fire (相对 now)
- 如果 (now - prev_fire).total_seconds() <= window_sec → 匹配
- 反之没到点或已经过去太久 (上一次触发 > window 之前)

边界:
- croniter.get_prev() 是严格小于的; now 恰好等于 cron 时刻时, prev 会跳到上个周期
  → 解决: 用 now + 1s 作为参考点, get_prev 就能拿到 "刚刚或正在的" 触发时刻
- timezone 必须与 scheduler 一致 (Asia/Shanghai); 调用方传入 timezone-aware datetime
"""

from __future__ import annotations

from datetime import datetime, timedelta

from croniter import croniter


def matches_in_window(
    cron_expr: str,
    now: datetime,
    window_sec: int = 60,
) -> bool:
    """判断 cron_expr 在 (now - window_sec, now] 区间内是否到点.

    Args:
        cron_expr: 5 段标准 cron (e.g. '0 9 * * 1' = 周一 9 点)
        now: 当前时间 (建议 timezone-aware)
        window_sec: 窗口宽度 (默认 60s; 与 cron_evaluator IntervalTrigger=1min 对齐)

    Returns:
        True 表示 cron 在过去 window_sec 秒内 (含 now) 到过点.
    """
    if not cron_expr:
        return False
    try:
        # +1 秒让 now 时刻恰好到点也算"到点"
        ref = now + timedelta(seconds=1)
        itr = croniter(cron_expr, ref)
        prev_fire = itr.get_prev(datetime)
    except (ValueError, KeyError):
        return False

    delta = now - prev_fire
    return timedelta(seconds=0) <= delta <= timedelta(seconds=window_sec)


def is_valid_cron(cron_expr: str) -> bool:
    """cron 语法校验 (T28 seeder / UI 编辑器复用)."""
    try:
        croniter(cron_expr, datetime.now())
        return True
    except (ValueError, KeyError):
        return False
