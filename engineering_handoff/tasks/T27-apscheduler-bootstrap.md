# T27 · APScheduler 接入 + lifespan 集成

## 1. 目标
把 APScheduler 4.x 嵌入 FastAPI 主进程；启动 6 个固定 jobs；与 v0.3 IM 后台任务并存。
Proposal: §7.3 模块 AT-C / §9.3 APScheduler 接入 / §9.6 部署形态 / 决策 AT-1

## 2. 范围
- **In**: APScheduler 选型 / 启停封装 / lifespan 集成 / 6 个固定 jobs 注册 / 健康检查
- **Out**: 具体 job 实现（cron_evaluator 见 T29 / withdraw_resolver 见 T31）

## 3. 调度器配置

```python
# v0.4 单实例配置
scheduler = AsyncIOScheduler(
    jobstores={'default': MemoryJobStore()},
    timezone='Asia/Shanghai',
    job_defaults={
        'coalesce': True,           # 重复触发合并
        'max_instances': 1,         # 同 job 不并发
        'misfire_grace_time': 300,  # 5min 误触延迟内仍然执行
    },
)
```

## 4. 注册的 6 个 jobs（占位 stub）

| Job ID | Trigger | 频率 | 实现位置 |
|---|---|---|---|
| `cron_evaluator` | IntervalTrigger(minutes=1) | 每分钟 | T29 |
| `threshold_scanner` | IntervalTrigger(minutes=15) | 每 15 分钟 | v0.4.2 |
| `withdraw_window_resolver` | IntervalTrigger(seconds=30) | 每 30 秒 | T31 |
| `skill_evolve_checker` | CronTrigger(hour=3) | 每天 03:00 | v0.4.2 |
| `quota_resetter` | CronTrigger(day=1, hour=0) | 每月 1 日 00:00 | v0.4.4 |
| `cleanup_audit_log` | CronTrigger(hour=4) | 每天 04:00 | T31 |

## 5. 组件分解

```
backend/src/auto_trigger/
├── scheduler.py             ← start_scheduler / shutdown_scheduler / get_scheduler
├── jobs/
│   ├── __init__.py
│   ├── stub.py              ← 各 job 占位，print log; T29/T31 才填真逻辑
│   └── health.py            ← scheduler.get_jobs() 数量校验
└── tests/
    └── test_scheduler_lifecycle.py

backend/src/main.py          ← lifespan() 加 start_scheduler() / shutdown_scheduler()
```

## 6. 状态管理
- scheduler 是模块级单例
- 测试模式下（`PYTEST_CURRENT_TEST` 存在）不启动后台调度，与 v0.3 IM bg tasks 一致

## 7. 必备状态（DoD）
- [ ] `from auto_trigger.scheduler import scheduler` 模块导入不抛错
- [ ] start_scheduler 后 `scheduler.get_jobs()` 返回 6 个
- [ ] shutdown_scheduler 优雅取消所有正在跑的 job
- [ ] lifespan 集成：FastAPI startup → scheduler 启动；shutdown → 优雅停止
- [ ] 与现有 v0.3 IM 后台任务在同一 event loop 上能稳定共存（跑 1 小时无错误）

## 8. 验收
- [ ] 单测覆盖：start → list jobs → shutdown 全流程
- [ ] 调度器在测试模式不启动
- [ ] 健康检查 endpoint `/healthz` 中新增 scheduler.running 字段返回
- [ ] 启动日志: `auto_trigger_scheduler_started job_count=6`
- [ ] 关闭日志: `auto_trigger_scheduler_stopped`

## 9. 已知陷阱
- APScheduler 4 API 与 3 不兼容；锁定 `apscheduler>=4.0,<5.0` 在 pyproject.toml
- AsyncIOScheduler 必须在已有 event loop 上启动；fastapi lifespan 已经在 loop 内，OK
- Timezone 设置必须早于任何 add_job；否则 cron 时间错位
- max_instances=1 + coalesce=True 防止"上次还没跑完，下次又触发"的重复执行
- misfire_grace_time=300 容忍 server 短暂停顿（5 min 内仍然执行漏过的 cron）

## 10. Claude Code 指令
顺序：先写 scheduler.py（pure setup）→ stub jobs（只 log，不做实事）→ lifespan 集成 → 跑 server 1 小时观察日志确认 jobs 都按时跑过 → 写测试。具体 job 逻辑由后续 task 替换 stub。
