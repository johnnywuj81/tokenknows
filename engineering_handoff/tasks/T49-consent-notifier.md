# T49 · ConsentNotifier (IM DM + Web 双通道)

> v0.5.1 第二块。把 T48 的 `initialize_pending` 转化为真实通知 → 用户收到 IM 私信 / web 铃铛角标。
> Proposal: [v0.5 §3.2 通知渠道 / OD-7](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
Skill 进入 `pending_contributor_consent` 时，给每位 contributor 发一条 IM DM + 一条 web 内 notification，引导他们点同意/拒绝（接 T50 endpoints）。

## 2. 范围
- **In**: 3 家 IM connector 的 send_dm 实现、统一 `notify_contributor` 入口、SSE 事件 `auto_trigger.consent_request`、web notification 表/字段
- **Out**: 用户点同意/拒绝的 endpoint（T50）、前端 UI（T51）

## 3. 通知触发时机

`skill_service.distill_skill` 完成 → `consent.initialize_pending(skill)` → 触发 `ConsentNotifier.notify_all(skill)` → 对每位 contributor 并发：
1. 尝试 IM DM（OD-7 主渠道）
2. 同时写 web notification（兜底，确保 contributor 即使 DM 失败也能看到）

## 4. IM DM API

| 平台 | API | 关键参数 |
|---|---|---|
| 飞书 | `POST im/v1/messages` body `{receive_id_type: "user_id", receive_id: <ou_xxx>, msg_type: "interactive", content: <card_json>}` | interactive card with 2 buttons |
| 钉钉 | `POST robot/send` user-level | ActionCard with 2 buttons |
| 企微 | `POST cgi-bin/message/send` text + button | text 含 link 跳 web 同意页 |

## 5. 消息模板（飞书 interactive card 示例）

```json
{
  "config": {"wide_screen_mode": true},
  "header": {"title": {"tag": "plain_text", "content": "🤖 你的 Skill 草稿等待确认"}},
  "elements": [
    {"tag": "div", "text": {"tag": "lark_md",
      "content": "**{skill.name}**\n\n基于你最近 30 天 {N} 条信号消息蒸馏\n主题: {topic_hint}"}},
    {"tag": "action", "actions": [
      {"tag": "button", "text": {"content": "✅ 同意发布"}, "type": "primary",
        "url": "{PUBLIC_BASE_URL}/skills/{skill.id}?action=sign"},
      {"tag": "button", "text": {"content": "❌ 拒绝"},
        "url": "{PUBLIC_BASE_URL}/skills/{skill.id}?action=reject"},
      {"tag": "button", "text": {"content": "🔍 查看详情"},
        "url": "{PUBLIC_BASE_URL}/skills/{skill.id}"}
    ]}
  ]
}
```

钉钉/企微同义降级（功能性 button，样式不同）。

## 6. Web Notification 数据模型

```python
# app/schemas/notification.py (新增模块)
class WebNotification(BaseModel):
    id: str
    user_id: str
    type: Literal["consent_request", "consent_signed", "consent_rejected", "consent_expired"]
    title: str
    body: str
    link_url: str
    read: bool = False
    created_at: datetime
    related_skill_id: str | None = None
```

`notifications` 表 schema:
```sql
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    related_skill_id TEXT,
    json TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_user_unread_idx
    ON notifications(user_id, read, created_at DESC);
```

## 7. 组件分解

```
backend/app/services/im/
├── consent_notifier.py        ← 主入口
│   ├── notify_all(skill) → list[NotificationResult]
│   ├── _notify_via_im_dm(skill, user_id) → bool (尝试 DM)
│   └── _notify_via_web(skill, user_id) → bool (写 notifications 表)
├── feishu_connector.py        ← 加 send_dm_interactive(user_id, card)
├── dingtalk_connector.py      ← 同上
├── wework_connector.py        ← 同上

backend/app/persistence/store.py  ← 加 upsert/list/mark_read notification 方法
backend/app/schemas/notification.py  ← 新建
backend/app/gateway/http_api/notifications.py  ← SSE 推送 + GET list

backend/tests/test_consent_notifier.py
backend/tests/test_im_dm_payload.py  ← 3 家 payload 正确性
```

## 8. 必备状态（DoD）
- [ ] 飞书 / 钉钉 / 企微 三家 DM 真实可发出（mock 测试 + 一次真发）
- [ ] DM 失败时 web notification 一定被写（兜底）
- [ ] SSE 事件 `auto_trigger.consent_request` 推送到当事 user_id（其他用户收不到）
- [ ] 通知含正确的 sign / reject URL，点击能进 T50 endpoint
- [ ] 同一 skill 对同一 contributor 不重复通知（去重检查）

## 9. 验收
- [ ] 端到端：触发自动 skill 蒸馏 → 看 contributor 收到 DM + web 铃铛 +1
- [ ] DM 失败 simulate (mock 4xx) → web notification 仍正确写入
- [ ] 飞书 interactive card 在飞书客户端能正常渲染（人工验收）
- [ ] notifications 表查询 user 未读 < 100ms（带索引）

## 10. 已知陷阱
- 飞书 `interactive` 消息要求**审批通过的 app 权限** `im:message:send_as_bot` + `im:message`；老应用可能没这个权限
- 钉钉 DM 用 OAuth `userid`（不是 `unionid`），与 PR/Issue webhook 里的 GitHub login 完全不同
- 企微 DM 是企业内部，不能跨企业；跨企业的 contributor 直接跳过 IM DM 走 web 兜底
- `receive_id_type` 飞书必须填正确（`open_id` vs `user_id`），错了返 400
- web notification 一次性 batch insert 多个 contributor 时用 executemany，避免 N 次 IO
- SSE 事件按 user_id 路由，不要广播给整 project（隐私）

## 11. Claude Code 指令
顺序：先写 `WebNotification` schema + `notifications` 表 + store 方法 → 写 `_notify_via_web` 完整路径 + 单测 → 飞书 `send_dm_interactive` + 单测 → 钉钉/企微 → `notify_all` 整合（DM 主，web 兜底）。最后做端到端集成测试 mock LLM + mock 3 家 IM。
