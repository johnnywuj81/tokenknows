# T31 · withdraw_window_resolver 后台任务 + cleanup

## 1. 目标
每 30 秒扫一次 trigger_execution 表，把 fire_at 已过的 scheduled 行交给 T30 dispatcher.fire()。同时实现 cleanup_audit_log 每天清理过期数据。
Proposal: §7.3 AT-C / §7.5 AT-E

## 2. 范围
- **In**: withdraw_window_resolver job、cleanup_audit_log job、扫描 + 派遣 + 错误恢复逻辑
- **Out**: dispatcher.fire() 本体（T30）、UI 撤回入口（T33）

## 3. 调度算法

```
每 30 秒 withdraw_window_resolver:
1. 拉 trigger_execution WHERE status='scheduled' AND fire_at <= now LIMIT 100
2. 对每行:
   a. SELECT FOR UPDATE 锁定该行（防多实例重复）
   b. 调 dispatcher.fire(execution_id)
   c. 写日志
3. 同时扫 status='scheduled' AND fire_at < now - 1 hour 的"僵尸"执行（dispatcher 也没接管）
   → 标记 status='expired'，写 audit_log
```

```
每天 04:00 cleanup_audit_log:
- DELETE FROM trigger_execution WHERE created_at < now - 90 days
- audit_log 表本身保留 2 年（合规，参见 v0.3 §11.4）
```

## 4. 组件分解

```
backend/src/auto_trigger/
├── jobs/
│   ├── withdraw_resolver.py   ← T27 stub 替换为真实实现
│   └── cleanup_audit.py
└── tests/
    ├── test_withdraw_resolver.py
    └── test_cleanup.py
```

## 5. 状态管理
- 用 PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` 作为分布式锁的轻量替代（v0.4 单实例足够；v0.5 多实例时迁移到 Redis lock）
- expired 状态作为兜底，防止某些 execution 永远卡在 scheduled

## 6. 必备状态（DoD）
- [ ] 每 30s 扫描耗时 < 100ms（100 条 scheduled execution）
- [ ] 同一 execution 不会被 fire 两次（FOR UPDATE 验证）
- [ ] 系统重启后能恢复扫描（execution 持久化）
- [ ] expired 状态正确处理：fire_at 过去 > 1h 的 scheduled → 自动 expired
- [ ] cleanup 不影响 audit_log 表

## 7. 验收
- [ ] 写一条 fire_at=now-1min scheduled 的 execution → 30s 内自动 fired（dispatcher 调通）
- [ ] 写一条 fire_at=now-2h scheduled 的 execution → 标 expired，不调 LLM
- [ ] 并发：同时 ground truth 启动 2 个 server instance → 同一 execution 只 fired 一次（v0.5 多实例验证）
- [ ] 单测覆盖 ≥ 80%

## 8. 已知陷阱
- SKIP LOCKED 在 PG 13+ 才支持；项目用 PG 15 OK
- 30 秒间隔 + 5 min 撤回窗口 → 用户可能感觉延迟，实际是设计 trade-off（频率太高浪费资源）
- expired 状态要触发 audit_log 通知 Owner，"为什么本该 fire 的没 fire"
- cleanup 不要 DELETE 太多行一次（用 LIMIT + 多次），避免锁全表
- 测试时 freezegun 跨进程时间不一致；用单进程测

## 9. Claude Code 指令
顺序：withdraw_resolver 先写 happy path → 加 FOR UPDATE → expired 兜底 → cleanup_audit 单独。性能测：插入 10000 条 scheduled execution，扫描耗时应 < 1s。
