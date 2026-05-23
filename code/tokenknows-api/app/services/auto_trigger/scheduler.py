"""APScheduler 包装 (v0.4 T27).

设计依据:
- Proposal §7.3 模块 AT-C / §9.3 APScheduler 接入
- T27-apscheduler-bootstrap.md

职责:
- 提供单例 AsyncIOScheduler
- start_scheduler() / shutdown_scheduler() 给 main.py lifespan 调
- 注册 6 个固定 job (T27 stub; cron_evaluator/withdraw_resolver 等真实逻辑由 T29/T30/T31 替换)

不在范围:
- 规则评估 (T29 RuleEvaluator)
- 撤回窗口 dispatcher (T30)
- 真实清理 / 配额重置 (v0.4.4)

决策偏差 (Proposal 4.x → 实际 3.x):
- Proposal 原写 APScheduler 4.x, 但 v4 仍 alpha (4.0.0a6), 改用稳定 3.10+
- API 兼容: AsyncIOScheduler / MemoryJobStore / CronTrigger / IntervalTrigger 都在 3.x 中可用
- 配置 (coalesce / max_instances / misfire_grace_time) 通过 job_defaults 传递
"""

from __future__ import annotations

import threading
from typing import Any

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.logging import logger
from app.services.auto_trigger import jobs as auto_trigger_jobs

_scheduler: AsyncIOScheduler | None = None
_lock = threading.Lock()

# 时区固定 Asia/Shanghai (v0.4 单实例; 多时区分布式留 v0.5)
SCHEDULER_TIMEZONE = "Asia/Shanghai"

# Job defaults (v0.4 Proposal §9.3 配置):
# - coalesce=True: 重启 / 漏触发 → 合并补一次, 不补 N 次
# - max_instances=1: 同 job 不允许并发执行 (防止上次没跑完, 下次又起)
# - misfire_grace_time=300: server 短暂停顿 5 min 内, 漏过的 cron 仍然补跑
JOB_DEFAULTS: dict[str, Any] = {
    "coalesce": True,
    "max_instances": 1,
    "misfire_grace_time": 300,
}


def start_scheduler() -> AsyncIOScheduler:
    """启动调度器并注册 6 个固定 job.

    幂等: 重复调用返回已存在实例.

    调用方: app/main.py lifespan startup (测试模式跳过).
    """
    global _scheduler
    with _lock:
        if _scheduler is not None and _scheduler.running:
            logger.info("auto_trigger_scheduler_already_running")
            return _scheduler

        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=SCHEDULER_TIMEZONE,
            job_defaults=JOB_DEFAULTS,
        )
        _register_fixed_jobs(_scheduler)
        _scheduler.start()
        logger.info(
            "auto_trigger_scheduler_started",
            timezone=SCHEDULER_TIMEZONE,
            job_count=len(_scheduler.get_jobs()),
        )
        return _scheduler


def shutdown_scheduler(wait: bool = False) -> None:
    """停止调度器. main.py lifespan shutdown 调.

    wait=False (默认): 不等正在跑的 job, 立即返回 (适合 server 关停).
    wait=True: 等所有 job 跑完 (适合优雅迁移).

    错误处理:
    AsyncIOScheduler.shutdown 内部用 event loop 的 call_soon_threadsafe;
    如果 loop 已 closed (e.g. test cleanup / FastAPI shutdown 后期), 会抛
    RuntimeError("Event loop is closed"). 这种场景下 GC 接管即可, 不抛.
    """
    global _scheduler
    with _lock:
        if _scheduler is None:
            return
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=wait)
            except RuntimeError as e:
                if "loop is closed" not in str(e).lower():
                    raise
                # event loop 已关闭, 让 GC 接管
                logger.debug("auto_trigger_scheduler_shutdown_loop_closed")
        logger.info("auto_trigger_scheduler_stopped")
        _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """返回当前 scheduler 实例 (None 表示未启动).

    健康检查 / 测试用. 不强制创建.
    """
    return _scheduler


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


# ─── 内部: 注册 6 个固定 job ───────────────────────────────


def _register_fixed_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 6 个 background job. job id 不能重复; replace_existing 防 hot-reload 重启时冲突.

    各 job 实现见 app/services/auto_trigger/jobs/__init__.py;
    T27 阶段是 stub (只 log + 占位), T29/T30/T31 替换为真逻辑.
    """
    # 1. cron 评估器 (T29 替换为真): 每分钟扫一次 enabled+mode=cron 的规则
    scheduler.add_job(
        auto_trigger_jobs.cron_evaluator_job,
        trigger=IntervalTrigger(minutes=1),
        id="cron_evaluator",
        replace_existing=True,
        name="规则评估 (cron)",
    )

    # 2. 阈值扫描器 (v0.4.2 真): 每 15 分钟扫一次累积阈值规则
    scheduler.add_job(
        auto_trigger_jobs.threshold_scanner_job,
        trigger=IntervalTrigger(minutes=15),
        id="threshold_scanner",
        replace_existing=True,
        name="阈值扫描 (threshold)",
    )

    # 3. 撤回窗口 resolver (T31 替换为真): 每 30 秒扫一次 status=scheduled 且 fire_at<=now
    scheduler.add_job(
        auto_trigger_jobs.withdraw_window_resolver_job,
        trigger=IntervalTrigger(seconds=30),
        id="withdraw_window_resolver",
        replace_existing=True,
        name="撤回窗口处理 (5min → fire)",
    )

    # 4. Skill 自进化检查 (v0.4.2 真): 每天 03:00
    scheduler.add_job(
        auto_trigger_jobs.skill_evolve_checker_job,
        trigger=CronTrigger(hour=3, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="skill_evolve_checker",
        replace_existing=True,
        name="Skill 自进化检查 (每天 03:00)",
    )

    # 5. 月配额重置 (v0.4.4 真): 每月 1 日 00:00
    scheduler.add_job(
        auto_trigger_jobs.quota_resetter_job,
        trigger=CronTrigger(day=1, hour=0, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="quota_resetter",
        replace_existing=True,
        name="月配额重置 (每月 1 日 00:00)",
    )

    # 6. 审计清理 (T31 真实现 sweep_expired + 90 天清理): 每天 04:00
    scheduler.add_job(
        auto_trigger_jobs.cleanup_audit_log_job,
        trigger=CronTrigger(hour=4, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="cleanup_audit_log",
        replace_existing=True,
        name="审计日志清理 (每天 04:00)",
    )

    # 7. T50 v0.5.1 · skill consent 30d 无响应 sweep: 每天 03:05 (避开 evolve 03:00)
    scheduler.add_job(
        auto_trigger_jobs.consent_sweep_expired_job,
        trigger=CronTrigger(hour=3, minute=5, timezone=SCHEDULER_TIMEZONE),
        id="consent_sweep_expired",
        replace_existing=True,
        name="Skill consent 超时清理 (每天 03:05)",
    )

    logger.debug("auto_trigger_jobs_registered", count=len(scheduler.get_jobs()))


__all__ = [
    "start_scheduler",
    "shutdown_scheduler",
    "get_scheduler",
    "is_running",
    "SCHEDULER_TIMEZONE",
]
