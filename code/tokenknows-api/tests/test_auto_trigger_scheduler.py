"""APScheduler 接入 (v0.4 T27).

覆盖:
- start_scheduler → 6 个固定 job 注册成功
- get_scheduler / is_running 状态查询
- shutdown_scheduler 优雅停止
- 重复 start 幂等
- 6 个 job stub 调用不抛异常 (即使数据库空)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services.auto_trigger import jobs as auto_trigger_jobs
from app.services.auto_trigger import scheduler as auto_trigger_scheduler


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个 test 一个独立 SQLite store; jobs 调 svc → svc 调 get_db → 用这个."""
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    yield s


@pytest.fixture(autouse=True)
def ensure_scheduler_clean():
    """每个 test 前后 scheduler 都是干净状态."""
    # 测前: 如果 module-global _scheduler 还存在 (前面 test 漏 shutdown), 清掉
    if auto_trigger_scheduler.is_running():
        auto_trigger_scheduler.shutdown_scheduler(wait=False)
    yield
    # 测后: 同理
    if auto_trigger_scheduler.is_running():
        auto_trigger_scheduler.shutdown_scheduler(wait=False)


# ─── start / shutdown / get_scheduler ────────────────────


@pytest.mark.asyncio
async def test_start_scheduler_registers_six_jobs():
    sched = auto_trigger_scheduler.start_scheduler()
    assert sched.running is True
    jobs = sched.get_jobs()
    job_ids = {j.id for j in jobs}
    assert job_ids == {
        "cron_evaluator",
        "threshold_scanner",
        "withdraw_window_resolver",
        "skill_evolve_checker",
        "quota_resetter",
        "cleanup_audit_log",
    }
    assert len(jobs) == 6


@pytest.mark.asyncio
async def test_start_scheduler_idempotent():
    s1 = auto_trigger_scheduler.start_scheduler()
    s2 = auto_trigger_scheduler.start_scheduler()
    assert s1 is s2  # 单例
    assert s1.running is True
    assert len(s1.get_jobs()) == 6  # 不重复注册


@pytest.mark.asyncio
async def test_shutdown_scheduler():
    sched = auto_trigger_scheduler.start_scheduler()
    assert sched.running is True
    auto_trigger_scheduler.shutdown_scheduler(wait=False)
    assert auto_trigger_scheduler.is_running() is False
    assert auto_trigger_scheduler.get_scheduler() is None


@pytest.mark.asyncio
async def test_shutdown_noop_when_not_running():
    """shutdown 在未启动时调用不抛异常."""
    assert auto_trigger_scheduler.is_running() is False
    auto_trigger_scheduler.shutdown_scheduler()  # 不应抛
    assert auto_trigger_scheduler.is_running() is False


@pytest.mark.asyncio
async def test_get_scheduler_none_before_start():
    """start 之前 get_scheduler 返回 None."""
    assert auto_trigger_scheduler.get_scheduler() is None


@pytest.mark.asyncio
async def test_scheduler_timezone():
    """时区应固定为 Asia/Shanghai (Q9 隐含决策)."""
    sched = auto_trigger_scheduler.start_scheduler()
    assert str(sched.timezone) == "Asia/Shanghai"


# ─── 6 个 job stub 调用 ───────────────────────────────────


@pytest.mark.asyncio
async def test_cron_evaluator_job_stub_no_throw():
    """T27 stub: 即使无规则也不抛异常."""
    await auto_trigger_jobs.cron_evaluator_job()


@pytest.mark.asyncio
async def test_threshold_scanner_job_stub_no_throw():
    await auto_trigger_jobs.threshold_scanner_job()


@pytest.mark.asyncio
async def test_withdraw_window_resolver_job_stub_no_throw():
    """T27 stub: 空库 (无 scheduled execution) 也不抛."""
    await auto_trigger_jobs.withdraw_window_resolver_job()


@pytest.mark.asyncio
async def test_skill_evolve_checker_job_stub_no_throw():
    await auto_trigger_jobs.skill_evolve_checker_job()


@pytest.mark.asyncio
async def test_quota_resetter_job_stub_no_throw():
    await auto_trigger_jobs.quota_resetter_job()


@pytest.mark.asyncio
async def test_cleanup_audit_log_job_real_impl():
    """T27 真实现 (与其他 stub 不同): 清理 90+ 天的 execution."""
    # 空库时应该 noop, 不抛
    await auto_trigger_jobs.cleanup_audit_log_job()


# ─── 集成: 启动后 stub job 异步触发不破坏 scheduler ─────


@pytest.mark.asyncio
async def test_scheduler_jobs_can_be_listed_with_next_run_time():
    """validates job triggers are computed (next_run_time 不应 None)."""
    sched = auto_trigger_scheduler.start_scheduler()
    for job in sched.get_jobs():
        assert job.next_run_time is not None, f"{job.id} 没下次触发时间"
