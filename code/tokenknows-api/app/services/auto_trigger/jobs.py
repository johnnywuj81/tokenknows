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
    """每分钟扫 enabled+mode=cron 的规则; T29 替换为真实 RuleEvaluator.

    Stub 行为: 仅记录扫描动作, 不评估规则.
    """
    try:
        rules = svc.list_rules(enabled=True, mode="cron", include_instance_defaults=True)
        logger.debug(
            "auto_trigger_cron_evaluator_tick",
            stub=True,
            candidate_rules=len(rules),
        )
    except Exception as e:
        logger.error("auto_trigger_cron_evaluator_failed", error=str(e))


async def threshold_scanner_job() -> None:
    """每 15 分钟扫 enabled+mode=threshold 的规则; v0.4.2 真实现.

    Stub 行为: 仅记录候选规则数量.
    """
    try:
        rules = svc.list_rules(enabled=True, mode="threshold", include_instance_defaults=True)
        logger.debug(
            "auto_trigger_threshold_scanner_tick",
            stub=True,
            candidate_rules=len(rules),
        )
    except Exception as e:
        logger.error("auto_trigger_threshold_scanner_failed", error=str(e))


async def withdraw_window_resolver_job() -> None:
    """每 30 秒扫 status=scheduled 且 fire_at<=now 的执行.

    T27 stub: 只读 + sweep_expired (兜底 expired); 不调 dispatcher.fire.
    T31 替换: 加 dispatcher 调度 + 单 FOR UPDATE 锁.
    """
    try:
        ready = svc.list_ready_to_fire(limit=100)
        if ready:
            logger.info(
                "auto_trigger_withdraw_resolver_ready",
                stub=True,
                count=len(ready),
                note="T31 will dispatch these to LLM",
            )
        # 兜底: scheduled 但 fire_at 过去 > 60min 仍未被 dispatch → 标 expired
        expired_n = svc.sweep_expired()
        if expired_n > 0:
            logger.warning(
                "auto_trigger_withdraw_resolver_expired",
                count=expired_n,
            )
    except Exception as e:
        logger.error("auto_trigger_withdraw_resolver_failed", error=str(e))


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
