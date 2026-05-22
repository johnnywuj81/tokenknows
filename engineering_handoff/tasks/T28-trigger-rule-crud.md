# T28 · TriggerRule CRUD + 4 条默认规则 seed

## 1. 目标
提供 TriggerRule 完整 CRUD + 4 条 v0.4 预置规则的 seeder。让用户首次启用 v0.4 时有现成规则可选。
Proposal: §7.4 模块 AT-D / 决策 AT-9 / 附录 A

## 2. 范围
- **In**: RuleService（业务层）、4 条预置规则 JSON、seeder 命令、规则评估时所需的辅助查询
- **Out**: API 路由（T32）、UI（T33）、cron_evaluator（T29）

## 3. 4 条预置规则

来自 Proposal 附录 A（v0.4.0 启动时由 seeder 写入 trigger_rule 表，project_id=NULL 表示实例级默认）：

| 规则 | mode | priority | enabled 默认 |
|---|---|---|---|
| 周一 09:00 自动周报 | cron | 50 | ✅ true |
| PR 含 architecture-decision → ADR | event | 85 | ⏸ false（v0.4.0 不实现 event 触发，规则先注册） |
| Issue incident → 复盘 | event | 100 | ⏸ false |
| 累积 50 章 → 自动书籍 | threshold | 70 | ⏸ false |

> v0.4.0 实际只有"周一周报"是 enabled 的，其他三条等对应版本支持。

## 4. 组件分解

```
backend/src/auto_trigger/
├── service/
│   ├── rule_service.py        ← create/update/delete/list/toggle
│   ├── validators.py          ← cron_expr 校验 / event_match schema 校验
│   └── seeder.py              ← seed_default_rules() 启动时调用
├── default_rules/
│   ├── weekly_report.json     ← 附录 A.1
│   ├── adr_pr.json            ← 附录 A.2
│   ├── incident_issue.json    ← 附录 A.3
│   └── book_threshold.json    ← 附录 A.4
└── tests/
    ├── test_rule_service.py
    ├── test_validators.py
    └── test_seeder.py
```

## 5. 状态管理
- 预置规则 project_id=NULL（实例级），用户首次启用 v0.4 时通过 onboarding API 复制到自己项目
- 规则更新走乐观锁 `updated_at` 字段防并发冲突

## 6. 必备状态（DoD）
- [ ] cron_expr 校验拒绝非法表达式（用 `croniter.is_valid()`）
- [ ] cooldown_seconds 最小值 60（防止规则风暴，Q AT-6）
- [ ] daily_cap 范围 1-100
- [ ] priority 范围 0-100
- [ ] event_match / threshold_spec JSONB 至少校验顶层字段必填
- [ ] seeder 幂等：重复跑不重复插入（用 INSERT ... ON CONFLICT DO NOTHING）

## 7. 验收
- [ ] 启动新空库 → seeder 自动插入 4 条 project_id=NULL 规则
- [ ] 重启 server → seeder 不重复插入（看日志确认）
- [ ] 创建一条违反 cooldown_seconds<60 的规则 → 400 错误
- [ ] toggle enabled → updated_at 自动刷新
- [ ] 单测覆盖率 ≥ 85%

## 8. 已知陷阱
- 预置规则的 description 必须中文清晰，因为会直接显示在 UI 引导向导（要素 #35）
- event_match 的 schema 不要做太严格的 JSON Schema 校验，留扩展余地；仅校验顶层必填
- threshold_spec 的 comparator 值集合：'>=', '<=', '==', '!=' 四种，不接受任意字符串
- 规则更新如果改 cron_expr，APScheduler 已注册的 job 需要 reschedule（这部分由 T29 cron_evaluator 处理，T28 只管表数据）

## 9. Claude Code 指令
顺序：validators.py（纯函数易测）→ rule_service.py CRUD → 4 条 JSON 文件（直接复制 Proposal 附录 A）→ seeder.py（启动时调）→ 接到 lifespan。完成后用 curl 直接验证 4 条默认规则存在。
