# T32 · Auto-Trigger REST API + SSE 推送

## 1. 目标
把 T28-T31 能力暴露为 REST API + 5 个新 SSE 事件类型。前端（T33-T35）可基于 OpenAPI 同步开发。
Proposal: §10 API 设计

## 2. 范围
- **In**: 4 组 REST 端点 + SSE 集成；OpenAPI 文档；权限校验中间件
- **Out**: UI 实现（T33-T35）；配额相关接口（v0.4.4）

## 3. 端点契约

v0.4.0 必须实现：

| 类别 | 端点 | 备注 |
|---|---|---|
| 规则 | `GET /api/projects/{pid}/auto-triggers/rules` | 列表 |
| 规则 | `GET /api/projects/{pid}/auto-triggers/rules/{rid}` | 详情 |
| 规则 | `PATCH /api/projects/{pid}/auto-triggers/rules/{rid}` | 启停 + 修改（v0.4.0 仅启停） |
| 执行 | `GET /api/projects/{pid}/auto-triggers/executions` | 历史时间轴 |
| 执行 | `GET /api/projects/{pid}/auto-triggers/executions/{eid}` | 详情 |
| 执行 | `POST /api/projects/{pid}/auto-triggers/executions/{eid}/cancel` | 撤回（仅 scheduled）|
| 执行 | `POST /api/projects/{pid}/auto-triggers/executions/{eid}/flag-false-positive` | 误触发标记 |
| 引导 | `GET /api/projects/{pid}/auto-triggers/onboarding` | 4 条预置规则预览 |
| 引导 | `POST /api/projects/{pid}/auto-triggers/onboarding` | 一键启用选中规则 |

v0.4.0 推迟（stub return 501）：
- POST/DELETE 规则（v0.4.3）
- Quota 接口（v0.4.4）

## 4. 权限矩阵

| 操作 | 角色要求 |
|---|---|
| 查看规则 / 执行 | 项目任意成员 |
| 启停规则（PATCH enabled） | Owner / Editor |
| 撤回 scheduled execution | Owner / Editor |
| 报告 false_positive | Owner / Editor / Reviewer |
| 一键启用 onboarding | 仅 Owner |

## 5. 组件分解

```
backend/src/api/routes/auto_trigger/
├── rules.py
├── executions.py
├── onboarding.py
└── __init__.py

backend/src/api/schemas/auto_trigger/   ← Pydantic v2 模型
├── rule.py
├── execution.py
└── ...

backend/src/api/deps/
└── auto_trigger_permissions.py        ← FastAPI dependency

backend/tests/api/auto_trigger/
└── test_*.py
```

## 6. SSE 集成

复用 MVP §6.2 SSE 通道，新增 5 个事件类型：

| 事件类型 | 触发 |
|---|---|
| `auto_trigger.scheduled` | T29 命中后立即推（撤回窗口开始） |
| `auto_trigger.fired` | T30 LLM 调用成功 |
| `auto_trigger.canceled` | 用户取消（POST cancel） |
| `auto_trigger.skipped` | cooldown / daily_cap / extra_condition 不满足 |
| `auto_trigger.failed` | LLM 失败 / execution.error_message |

事件 payload 含 execution_id / rule_id / project_id / type / signal_summary，前端可挂通知卡。

## 7. 必备状态（DoD）
- [ ] OpenAPI 自动生成；schema 字段名与前端约定（snake_case JSON）
- [ ] 所有端点权限测试覆盖（403 / 404）
- [ ] cancel 操作要求 execution.status='scheduled'，已 fired 的拒绝（409 Conflict）
- [ ] SSE 事件能被前端 EventSource 订阅到（端到端测）

## 8. 验收
- [ ] Postman / httpie 跑通 happy path
- [ ] cancel 在 fire_at 已过的 execution 上 → 拒绝（已过撤回窗口）
- [ ] onboarding POST 后能在 list 看到新启用的规则
- [ ] OpenAPI 在 `/docs` 渲染、字段说明完整
- [ ] 单测覆盖率 ≥ 80%

## 9. 已知陷阱
- 撤回操作的并发问题：用户点撤回的同时 T31 resolver 也在拉 fire → SELECT FOR UPDATE 协调
- onboarding 是项目级 copy：把 project_id=NULL 的预置规则 INSERT 一份 project_id=当前 的副本，**不要**让多个项目共用同一行
- SSE 事件不要在 db transaction 内推送（事务还没 commit 时前端就收到事件会导致状态不一致），用 after-commit hook
- 列表分页用 cursor（execution.id），不要用 OFFSET（性能差）

## 10. Claude Code 指令
按 OpenAPI-first：schemas/ 先写完 → 自动出 OpenAPI 给 T33-T35 同步开工 → 再补 routes 实现 → 测试。SSE 集成留最后，先用 polling 测通逻辑。
