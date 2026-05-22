# T23 · IM REST API（连接 / 群 / 统计 / SignalGate / Webhook）

## 1. 目标
把 T17-T22 的能力暴露为 REST API，给前端（T24-T25）和外部 webhook 用。
Proposal: §10 API 设计

## 2. 范围
- **In**: 11 组端点（连接 / 群 / 消息查询 / SignalGate / 同意书 stub / 按需蒸馏 / Webhook）
- **Out**: 实际 UI（T24-T25）、同意书前端流程（v0.3.1）

## 3. 端点契约

完整列表见 Proposal §10。v0.3.0 必须实现：

| 类别 | 端点 | 备注 |
|---|---|---|
| 连接 | `POST /api/projects/{pid}/im/connections` | 返回 authorize_url |
| 连接 | `GET /api/projects/{pid}/im/connections` | 列出 + 状态 |
| 连接 | `PATCH /api/projects/{pid}/im/connections/{cid}` | 暂停/恢复 |
| 连接 | `DELETE /api/projects/{pid}/im/connections/{cid}` | 撤回（触发 T22） |
| 群 | `GET /api/projects/{pid}/im/connections/{cid}/chats` | 含 status filter |
| 群 | `POST .../chats/{platform_chat_id}/join` | 邀请 bot |
| 群 | `POST .../chats/{cid}/leave` | 踢 bot |
| 群 | `GET /api/.../im/chats/{chat_id}/stats` | signal rate / TOP contributors |
| 消息 | `GET /api/.../im/chats/{chat_id}/messages` | 默认不含 content_text |
| SignalGate | `GET/PATCH /api/.../im/signal/config` | 阈值 |
| SignalGate | `POST /api/.../im/signal/recompute` | 触发重算 |
| 蒸馏 | `POST /api/.../im/distill` | 按需 |
| Webhook | `POST /api/webhooks/feishu/events/{tenant_key}` | T19 已部分实现 |
| Webhook | `POST /api/webhooks/feishu/auth-callback` | T18 已实现 |

v0.3.0 推迟：同意书相关 5 个端点（stub return 501）。

## 4. 权限矩阵

| 操作 | 角色要求 |
|---|---|
| 创建/管理 personal connection | 项目任意成员 |
| 查看 connection 列表 | 项目任意成员，但只看到自己创建的 |
| 邀请 bot 入群 / 踢 bot | connection 创建者本人 |
| 查看消息原文 (`include_content=true`) | 发送者本人 + 项目 Owner（审计） |
| SignalGate 配置 | Owner / Editor |
| 按需蒸馏 | 项目 Editor+ |

## 5. 组件分解

```
backend/src/api/routes/im/
├── connections.py
├── chats.py
├── messages.py
├── signal.py
├── distill.py
├── stats.py
├── consents.py              ← stub return 501
└── webhooks/
    ├── feishu_auth.py       ← T18
    └── feishu_events.py     ← T19

backend/src/api/schemas/im/  ← Pydantic v2 模型
├── connection.py
├── chat.py
├── message.py
└── ...

backend/src/api/deps/
└── im_permissions.py        ← FastAPI dependency: 权限校验

backend/tests/api/im/
└── test_*.py                ← 每个路由 happy + 权限 + 错误码
```

## 6. SSE 推送

复用 MVP §6.2 SSE 通道，新增事件类型：
- `im.message.received` (聚合摘要，每 30s 一次)
- `im.signal.computed`
- `im.distill.completed`

## 7. 必备状态（DoD）
- [ ] OpenAPI 自动生成；schema 字段名与前端约定（snake_case JSON）
- [ ] 所有端点权限测试覆盖（403 / 404 都有用例）
- [ ] 错误返回统一格式 `{ error: { code, message, details } }`
- [ ] 分页统一 `?cursor / ?page_size`
- [ ] include_content=true 需 audit_log 记录

## 8. 验收
- [ ] Postman / httpie 跑通 happy path
- [ ] include_content=true 没权限 → 403
- [ ] 撤回授权后再调任何端点 → 404 或 410
- [ ] OpenAPI 在 `/docs` 能渲染、字段说明完整
- [ ] 前端在 T24-T25 中只看 OpenAPI 文档就能接

## 9. 已知陷阱
- 消息查询接口默认不返回 content_text；前端要展示要 explicit ?include_content=true，且需权限
- chat stats 的 signal_rate 是 30 天滑动窗口，缓存 5 分钟（在 redis）
- distill API 返回 task_id 后，结果走 SSE `im.distill.completed` 推送；前端不要 poll
- Webhook 路径里的 tenant_key 是飞书的多租户 key，要校验在数据库里有对应 connection，否则返回 404 防扫描

## 10. Claude Code 指令
按 OpenAPI-first：先在 schemas/ 写完所有 Pydantic 模型 → 自动出 OpenAPI → 让前端 T24-T25 同步开工。再补 routes 实现。每写完一个 router 立刻补对应 test_*.py。
