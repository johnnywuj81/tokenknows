# T26 · Auto-Trigger 数据库 Schema 与 Migration

## 1. 目标
为 v0.4 自动触发建立数据库基础设施。新增 3 张表（trigger_rule / trigger_execution / generation_quota）+ asset 表 patch。是所有后续 task 的前置。
Proposal: §8 数据模型

## 2. 范围
- **In**: 4 个 migration 文件、ORM 模型、DAO 层基础查询、单测
- **Out**: 真实规则数据 seeding（T28 做）、Quota 完整逻辑（v0.4.4 才实现）

## 3. 数据契约（Migration 文件）

`backend/migrations/v0.4/`:

| 文件 | 内容 |
|---|---|
| `20260522_v04_01_trigger_rule.sql` | Proposal §8.1 DDL；JSONB 字段含 cron_expr / event_match / threshold_spec |
| `20260522_v04_02_trigger_execution.sql` | Proposal §8.2；含状态机 / 信号溯源 / 用户反馈字段 |
| `20260522_v04_03_generation_quota.sql` | Proposal §8.3；按月一行 UNIQUE (project_id, year_month) |
| `20260522_v04_04_asset_patch.sql` | ALTER asset ADD trigger_meta JSONB / trigger_execution_id |

## 4. 索引清单

- `trigger_rule`: `(enabled, mode) WHERE enabled=true` — RuleEvaluator 主查询路径
- `trigger_rule`: `(project_id)` — UI 列表
- `trigger_execution`: `(status, fire_at) WHERE status='scheduled'` — withdraw_resolver 扫描
- `trigger_execution`: `(project_id, created_at DESC)` — 历史时间轴
- `trigger_execution`: `(rule_id, created_at DESC)` — 单规则历史
- `generation_quota`: UNIQUE `(project_id, year_month)`
- `asset`: `(trigger_execution_id) WHERE trigger_execution_id IS NOT NULL` — 反查触发执行

## 5. 组件分解

```
backend/src/auto_trigger/
├── models/
│   ├── trigger_rule.py        ← SQLAlchemy ORM + Pydantic schema
│   ├── trigger_execution.py
│   └── generation_quota.py
├── dao/
│   ├── rule_dao.py            ← CRUD + 按 enabled + mode 查询
│   ├── execution_dao.py       ← 写 scheduled / fired / canceled 等
│   └── quota_dao.py           ← v0.4.0 占位 (仅读, 不增不减)
└── schemas/
    └── enums.py               ← TriggerMode / ExecutionStatus / SkipReason

backend/migrations/v0.4/*.sql
backend/tests/auto_trigger/test_dao.py
```

## 6. 状态管理
N/A（纯后端基础设施）

## 7. 必备状态（DoD）
- [ ] alembic upgrade / downgrade 都能跑
- [ ] JSONB 字段 round-trip 测试（写入复杂 dict 后读出一致）
- [ ] ExecutionStatus 状态机的合法转换枚举（scheduled → fired / canceled / skipped / failed / expired）
- [ ] DAO 单测覆盖率 ≥ 80%

## 8. 验收
- [ ] DDL 与 Proposal §8 字段名/类型 100% 一致
- [ ] `EXPLAIN ANALYZE` 关键查询走索引（不走 Seq Scan）：
  - 按 enabled+mode 拉 active rule
  - 按 status='scheduled' 扫即将 fire 的 execution
- [ ] 不破坏现有 asset 查询路径（跑一遍 MVP 测试）
- [ ] trigger_execution.signal JSONB 支持任意嵌套（不限 schema）

## 9. 已知陷阱
- trigger_rule.project_id 允许 NULL（实例级默认规则），UNIQUE (project_id, name) 在 PG 默认认为 NULL ≠ NULL，需要 `UNIQUE NULLS NOT DISTINCT`（PG15+）或 partial index 处理
- generation_quota year_month TEXT 而非 DATE，简化按月聚合（'2026-05'）
- asset.trigger_meta 添加时给默认 NULL，避免现有数据 round-trip 破坏
- JSONB 查询性能：trigger_execution.signal 不加 GIN 索引（v0.4.0 不查），v0.4.3 再考虑

## 10. Claude Code 指令
先写 SQL → 跑 migration → 再写 ORM → 再写 DAO → 最后写测试。状态机用 `Literal[...]` 类型 + helper 函数校验非法转换。
