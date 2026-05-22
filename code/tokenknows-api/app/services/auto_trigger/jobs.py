"""6 个固定 background job (v0.4 T27 stub).

各 job 当前是 stub: 只 log + 必要时 sweep_expired (兜底); 真实逻辑由后续 task 替换:
- cron_evaluator → T29 (RuleEvaluator)
- threshold_scanner → v0.4.2
- withdraw_window_resolver → T31 (调 dispatcher.fire)
- skill_evolve_checker → v0.4.2
- quota_resetter → v0.4.4
- cleanup_audit_log → T31 (90 天清理)

约定:
- 所有 job 必须 async def
- 异常不能向 APScheduler 抛 (导致 job 被 unschedule), 在 try/except 内捕获 + 记 log
- 单次执行延迟应 < 10s, 重活推到 ThreadPoolExecutor / 子 task
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config.logging import logger
from app.services import auto_trigger_service as svc


async def cron_evaluator_job() -> None:
    """每分钟扫 enabled+mode=cron 的规则 (T29 真实现).

    实际评估委托给 evaluator.evaluate_cron_rules:
    - CronMatcher: 是否在 60s 窗口内到点
    - 实例级规则 fan-out 到所有 active project (events 表)
    - 三层防护: cooldown / daily_cap / extra_condition
    - 命中 → svc.schedule_execution (5min 撤回窗口); 否则 svc.record_skip
    """
    try:
        from app.services.auto_trigger.evaluator import evaluate_cron_rules
        evaluate_cron_rules()
        # 详细 stats log 由 evaluate_cron_rules 内部写 (auto_trigger_cron_evaluator_done)
    except Exception as e:
        logger.error("auto_trigger_cron_evaluator_failed", error=str(e), exc_info=True)


async def threshold_scanner_job() -> None:
    """每 15 分钟扫 enabled+mode=threshold 的规则 (v0.4.2 T41 真实现).

    实际评估委托给 evaluator.evaluate_threshold_rules:
    - 拉 enabled+mode=threshold 规则
    - 实例级 fan-out 到所有 active 项目 (events 表)
    - 检查 ThresholdSpec (metric 比较 + and_not_exists 去重)
    - 三层防护: cooldown / daily_cap / unsupported_metric
    - 命中 → svc.schedule_execution (5min 撤回窗口)
    """
    try:
        from app.services.auto_trigger.evaluator.threshold_evaluator import (
            evaluate_threshold_rules,
        )
        evaluate_threshold_rules()
        # 详细 stats log 由 evaluate_threshold_rules 内部写
    except Exception as e:
        logger.error(
            "auto_trigger_threshold_scanner_failed",
            error=str(e), exc_info=True,
        )


async def withdraw_window_resolver_job() -> None:
    """每 30 秒扫 status=scheduled 且 fire_at<=now 的执行 (T30+T31 真实现).

    流程:
    1. 拉一批 ready_to_fire 执行 (撤回窗口已过, 用户未取消)
    2. 串行调 dispatcher.fire_batch → 真调 LLM 生成 asset
    3. 兜底: scheduled 但 fire_at 过去 > 60min 仍未处理 → 标 expired (避免堆积)
    """
    try:
        from app.services.auto_trigger.dispatcher import fire_batch

        ready = svc.list_ready_to_fire(limit=100)
        if ready:
            execution_ids = [e.id for e in ready]
            stats = await fire_batch(execution_ids)
            logger.info(
                "auto_trigger_withdraw_resolver_dispatched",
                ready=len(ready),
                **stats,
            )

        # 兜底: 长期 scheduled 标 expired
        expired_n = svc.sweep_expired()
        if expired_n > 0:
            logger.warning(
                "auto_trigger_withdraw_resolver_expired",
                count=expired_n,
            )
    except Exception as e:
        logger.error("auto_trigger_withdraw_resolver_failed", error=str(e), exc_info=True)


async def skill_evolve_checker_job() -> None:
    """每天 03:00 检查 Skill 自进化候选; v0.4.2 真实现.

    Stub 行为: 仅 log 触发时刻.
    """
    try:
        logger.info(
            "auto_trigger_skill_evolve_checker_tick",
            stub=True,
            note="v0.4.2 will check usage_count >= 20 AND acceptance_rate < 0.5",
        )
    except Exception as e:
        logger.error("auto_trigger_skill_evolve_checker_failed", error=str(e))


async def quota_resetter_job() -> None:
    """每月 1 日 00:00 重置项目月配额计数; v0.4.4 真实现.

    Stub 行为: 仅 log 触发时刻 + 当前月份.
    """
    try:
        now = datetime.now(timezone.utc)
        logger.info(
            "auto_trigger_quota_resetter_tick",
            stub=True,
            year_month=now.strftime("%Y-%m"),
            note="v0.4.4 will reset generation_quotas counters",
        )
    except Exception as e:
        logger.error("auto_trigger_quota_resetter_failed", error=str(e))


async def cleanup_audit_log_job() -> None:
    """每天 04:00 清理 90+ 天的 trigger_execution; audit_log 表本身保留 2 年.

    T27 真实现: 直接调 store.delete_old_trigger_executions.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        from app.persistence import get_db
        deleted = get_db().delete_old_trigger_executions(cutoff.isoformat())
        if deleted > 0:
            logger.info("auto_trigger_audit_log_cleaned", deleted=deleted)
        else:
            logger.debug("auto_trigger_audit_log_clean_noop")
    except Exception as e:
        logger.error("auto_trigger_cleanup_audit_log_failed", error=str(e))


__all__ = [
    "cron_evaluator_job",
    "threshold_scanner_job",
    "withdraw_window_resolver_job",
    "skill_evolve_checker_job",
    "quota_resetter_job",
    "cleanup_audit_log_job",
]
