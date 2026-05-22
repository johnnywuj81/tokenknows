# T29 · cron_evaluator + RuleEvaluator

## 1. 目标
每分钟扫所有 enabled+mode=cron 的规则，判断是否到达 cron_expr 触发时间。命中 → 调 TriggerDispatcher。
Proposal: §7.1 模块 AT-A / §7.3 AT-C / 决策 AT-3

## 2. 范围
- **In**: RuleEvaluator 主类、cron_expr 解析、附加条件评估（extra_condition）、与 dispatcher 协作
- **Out**: dispatcher 本体（T30）、threshold_scanner（v0.4.2）、event_match 评估器（v0.4.1）

## 3. 评估算法

```
每分钟 cron_evaluator 触发:
1. 拉所有 enabled=true AND mode='cron' 的 rule
2. 对每条 rule:
   a. 用 croniter 计算上次"到点"时间（在过去 1 分钟内）
   b. 如果到点了:
      i.   检查 cooldown（distinct(last_fired_at) >= cooldown_seconds 前）
      ii.  检查 daily_cap（今天 fired 次数 < daily_cap）
      iii. 检查 extra_condition（如 "events_last_7d >= 30"）
      iv.  全通过 → 写 trigger_execution{status=scheduled, fire_at=now+5min}
      v.   通过 SSE 推 auto_trigger.scheduled 事件
      vi.  否则写 trigger_execution{status=skipped, skip_reason=...}
3. 返回扫描统计（命中/跳过/失败数）
```

## 4. 组件分解

```
backend/src/auto_trigger/
├── evaluator/
│   ├── rule_evaluator.py      ← 主流程
│   ├── cron_matcher.py        ← croniter 包装；判断是否在 [now-1min, now] 区间内到点
│   ├── conditions.py          ← extra_condition 评估（events_last_7d 等指标查询）
│   └── cooldown_guard.py      ← Redis-backed cooldown lock + daily_cap counter
├── jobs/
│   └── cron_evaluator.py      ← T27 的 stub 替换为真实实现
└── tests/
    ├── test_rule_evaluator.py ← freezegun 模拟时间点
    ├── test_cron_matcher.py
    └── test_conditions.py
```

## 5. 状态管理
- cooldown / daily_cap 计数走 Redis（key: `auto_trigger:rule:{id}:fired_at_{date}`）
- 没有 Redis 时降级到 trigger_execution 表 SQL 查询（性能稍差，可接受）

## 6. 必备状态（DoD）
- [ ] 模拟周一 09:00 触发"周一周报"规则 → 命中、写 scheduled、SSE 推送
- [ ] 模拟周二 09:00 触发 → 不命中（cron 不到点）
- [ ] 模拟周一 09:00 第二次扫描（同一分钟内多次）→ 第二次因 cooldown 跳过
- [ ] extra_condition 为 events_last_7d >= 30 但项目上周事件 = 5 时 → skip
- [ ] 评估失败（DB / Redis 错）不阻塞其他规则，独立 try/except

## 7. 验收
- [ ] 用 freezegun 模拟 1 周时间线，"周一周报"规则触发次数 == 1
- [ ] 100 条规则评估耗时 < 200ms（性能基线，Proposal 附录 B）
- [ ] 通过 SSE 端到端：scheduled 事件能被前端订阅到
- [ ] 单测覆盖 ≥ 85%

## 8. 已知陷阱
- croniter 的"上次到点"和"下次到点"语义易混淆，仔细测边界（如刚好在整分钟）
- 同分钟内 cron_evaluator 被 APScheduler 触发多次（极少见但可能）：用 coalesce=True + max_instances=1 防御
- extra_condition 的指标查询要走索引；events_last_7d 走 `events(project_id, created_at DESC)` 索引
- 跨日 daily_cap 重置：用 'auto_trigger:rule:{id}:fired_at_2026-05-22' 这种带日期 key，到日自动失效（TTL=48h）
- 评估失败要落 audit_log，否则用户不知道为什么本该触发的规则没触发

## 9. Claude Code 指令
顺序：cron_matcher（纯函数）→ test_cron_matcher 用 freezegun → conditions（带 DB）→ cooldown_guard（带 Redis）→ rule_evaluator 组装 → 接到 T27 cron_evaluator job。每写完一段用真实周一时间戳测一遍。
