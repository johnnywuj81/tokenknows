# T22 · 数据保留期与撤回流程

## 1. 目标
落实 90 天原始消息保留期 + 用户撤回授权的数据清理（合规硬要求）。
Proposal: 决策 IM-14 / §7.4 IM-D / §11.5 出域控制 / §12 R10

## 2. 范围
- **In**: 90 天到期清理 cron / 撤回授权触发清理 / 到期前 7 天通知 / 撤回后 ValueSegment 匿名化
- **Out**: 同意书签字流程（v0.3.1，本任务只准备表结构和 API stub）

## 3. 时间线契约

| 事件 | 行为 |
|---|---|
| 消息入库 | `retention_until = received_at + 90 days` |
| 到期前 7 天 | 给 connection 创建者发通知"X 天后将清理 Y 条消息，需延期请..."（v0.3.0 仅 UI 提示，不发邮件） |
| 到期 | cron 删除 `WHERE retention_until < now() AND redacted = false`（不删派生 ValueSegment） |
| 用户撤回授权 | 立即标记 connection.status='revoked'；启动 30 天后强制清理 task |
| 用户撤回同意（v0.3.1） | ValueSegment.contributors[].anonymized=true；30 天后清理该用户的原始消息 |

## 4. 组件分解

```
backend/src/im/retention/
├── cleaner.py               ← 主清理逻辑：扫到期消息、批量删除、写 audit
├── notifier.py              ← 到期前通知（v0.3.0 写 UI notification 表，发邮件留 v0.3.1）
├── revocation.py            ← 撤回流程：connection.revoke() / consent.revoke()
└── anonymizer.py            ← ValueSegment.contributors 匿名化

backend/src/workers/
└── im_retention_worker.py   ← APScheduler / Celery beat:
                              ← 每日 03:00 跑 cleaner
                              ← 每日 09:00 跑 notifier（提前 7 天）
                              ← revocation 30 天延迟队列

backend/src/api/routes/
└── im_retention.py          ← DELETE /api/.../im/connections/{cid} 增强：触发 30 天清理 task
                              ← POST /api/.../im/connections/{cid}/extend：延长保留期（最多 +90 天）

backend/tests/im/retention/
├── test_cleaner.py          ← freeze_time 测到期
├── test_notifier.py
└── test_revocation.py
```

## 5. 状态管理
- 撤回授权后的 30 天保留窗口存在 `im_connection.revoked_at` + `scheduled_purge_at`
- 用户在 30 天内可"恢复"（不在 v0.3.0 范围，但表字段预留）

## 6. 必备状态（DoD）
- [ ] cleaner 每次跑前后写 audit_log：删了哪个 chat 多少条
- [ ] 删除走批量（每批 1000 条），避免锁表
- [ ] 删除 im_message 前用 m月分区 DETACH 后 DROP，加速
- [ ] 撤回授权 → 立即停止订阅（不再有新消息进） + 30 天后物理删除
- [ ] notifier 每条消息只发一次（用 `notified_at` 字段去重）

## 7. 验收
- [ ] 单测用 freezegun 跑 91 天后场景，消息被清理
- [ ] 派生 ValueSegment **不被删**（PII 已脱敏 + 已聚合，属于派生数据）
- [ ] 撤回授权后 30 天内重新授权 → 历史数据**不恢复**（30 天到期前已物理删）
- [ ] audit_log 完整：`im.retention.cleaned` 事件含 chat_id / count / deleted_at
- [ ] 延长保留期 API 限 admin 调用

## 8. 已知陷阱
- 月分区 DETACH 比 DELETE 快 100x，但要保证整月数据都过期；不整月用 DELETE
- 跨时区：retention_until 用 UTC，cleaner 跑在 UTC 03:00 / 用户时区凌晨可能差异
- ValueSegment 引用的 im_message_ids 在原消息删除后会变成"悬空指针"，前端展示证据链时要兜底（"原始消息已按保留期清理"）
- 通知到达时机：to email 是 v0.3.1，v0.3.0 只在 web 内显示
- 法律要求：清理日志本身要保留更久（建议 2 年），不能因清理消息而把审计日志一并清

## 9. Claude Code 指令
先写 cleaner.py + 单测（freezegun 模拟 91 天后）→ 验证分区 DETACH/DROP 流程 → notifier → revocation。anonymizer 留 v0.3.1 用，本任务只写空函数 + TODO。
