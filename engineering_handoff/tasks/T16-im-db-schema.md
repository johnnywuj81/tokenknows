# T16 · IM 数据库 Schema 与 Migration

## 1. 目标
为 v0.3 IM 知识蒸馏建立数据库基础设施。新增 4 张表（IMConnection/IMChat/IMMessage/IMConsent）+ ValueSegment/Skill patch。是所有后续 task 的前置。
Proposal: §8 数据模型

## 2. 范围
- **In**: 6 个 migration 文件、DAO 层基础查询、单测
- **Out**: 真实数据接入（T18+ 才发生）、数据 seeding

## 3. 数据契约（Migration 文件）

`backend/migrations/v0.3/`:

| 文件 | 内容 |
|---|---|
| `20260522_01_im_connection.sql` | Proposal §8.1 完整 DDL；含加密字段 `*_enc BYTEA` |
| `20260522_02_im_chat.sql` | §8.2；UNIQUE (connection_id, platform_chat_id) |
| `20260522_03_im_message.sql` | §8.3；**按 received_at 月分区**（pg_partman 或手动） |
| `20260522_04_im_consent.sql` | §8.4；UNIQUE (project_id, platform, platform_user_id) |
| `20260522_05_value_segment_patch.sql` | ALTER TABLE 加 `source_type / source_mode / im_chat_id / im_message_ids / contributors` |
| `20260522_06_skill_patch.sql` | ALTER TABLE 加 `source_segment_ids / contributors` |

## 4. 索引清单

- `im_connection`: `(status) WHERE status NOT IN ('revoked')`
- `im_chat`: `(connection_id, status)`
- `im_message`:
  - `(chat_id, sent_at DESC)` — 时间序拉取
  - `(chat_id, is_signal, sent_at DESC) WHERE is_signal=true` — SignalGate 后查询
  - `(retention_until) WHERE redacted=false` — 保留期清理扫描
- `im_consent`: `(project_id, status)`

## 5. 组件分解

```
backend/src/im/
├── models/
│   ├── connection.py        ← SQLAlchemy ORM
│   ├── chat.py
│   ├── message.py
│   └── consent.py
├── dao/
│   ├── connection_dao.py    ← CRUD + 加密字段透明加解密
│   ├── chat_dao.py
│   ├── message_dao.py       ← 批量插入、按时间区间查询
│   └── consent_dao.py
└── crypto.py                ← AES-256-GCM 包装（用 KMS 主密钥）

backend/migrations/v0.3/*.sql
backend/tests/im/test_dao.py
```

## 6. 状态管理
N/A（纯后端基础设施）

## 7. 必备状态（DoD）
- [ ] `alembic upgrade head` 在空库 / 已有 MVP 数据库上都能跑过
- [ ] `alembic downgrade -1` 不报错，能还原
- [ ] 分区自动按月创建（pg_partman 配置 + 单测覆盖跨月场景）
- [ ] 加密字段写入 → 读出 → 解密能 round-trip
- [ ] DAO 单测覆盖率 ≥ 80%

## 8. 验收
- [ ] DDL 与 Proposal §8 字段名/类型 100% 一致
- [ ] `EXPLAIN ANALYZE` 关键查询走索引（不走 Seq Scan）：
  - 按 chat_id + 时间区间拉消息
  - 按 retention_until 扫即将到期
- [ ] crypto.py 用项目统一 KMS 接口（不要新造一套）
- [ ] 不破坏 MVP 现有 ValueSegment / Skill 查询路径（跑一遍现有测试）

## 9. 已知陷阱
- pg_partman 在 PG 15 上需要 `CREATE EXTENSION pg_partman`，私有化部署清单里要加
- `im_message` 表会很大（百万级/月），分区必须做；不分区后续 retention 清理会全表扫
- `mentions TEXT[]` GIN 索引按需加（T19 频繁查 @ 自己的消息时再加）
- ValueSegment.patch 加字段时给默认值 `source_type='event'`，避免现有数据 NULL 异常

## 10. Claude Code 指令
先写 SQL → 跑 migration → 再写 ORM → 再写 DAO → 最后写测试。crypto.py 写完先单独跑加解密 round-trip，再被 DAO 引用。
