# T51 · Skill Consent 前端 (Banner + 全局 Notification)

> v0.5.1 第四块（也是 v0.5 全部任务的最后一块）。让 contributor 在 Web 完成同意流程。
> Proposal: [v0.5 §3.4 Alice 视角](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
Alice 打开 TokenKnows → 顶部铃铛角标 → 点开看 SKILL.md → 同意/拒绝两键 → 立即反馈 + 跳走。

## 2. 范围
- **In**: Skill 详情页 banner、AppLayout 顶层铃铛 + 通知中心 Popover、sign/reject 按钮 + 二次确认 dialog、SSE 订阅
- **Out**: 后端 endpoint（T50）、IM 通知（T49）

## 3. 路由

- 已有：`/projects/:id/skills/:skill_id` Skill 详情页
- 新加 query param：`?action=sign|reject` 跳入直接打开二次确认 dialog（IM DM 跳链接专用）
- 新加全局：`AppLayout` 顶部右侧加 `<NotificationBell />`（聚合所有 type）

## 4. 组件分解

```
src/features/skills/
├── components/
│   ├── ConsentPending.tsx           ← Skill 详情页顶部 banner (status=pending 时显示)
│   ├── ConsentDialog.tsx            ← 二次确认弹窗 (sign/reject)
│   └── ConsentRejectReasonField.tsx ← reject 时强制输入 ≥ 5 字符理由

src/features/notifications/
├── NotificationBell.tsx             ← 顶层铃铛 + 角标 + Popover
├── NotificationList.tsx             ← Popover 内的通知列表
├── NotificationItem.tsx             ← 单条通知 (含 consent_request 类型)
└── hooks/
    ├── useUnreadCount.ts
    ├── useNotifications.ts
    └── useNotificationSSE.ts        ← 订阅 SSE auto_trigger.consent_* 4 事件
```

## 5. UI 视觉

### ConsentPending banner（Skill 详情页顶部）

```
🟡 等待 contributor 同意发布
   还差 1/3 contributor 签字 · 截止 2026-06-22

   [👍 同意发布]  [👎 拒绝]
   (按钮仅当前 user 是 contributor 时显示)
```

颜色：黄色边框 + 浅黄底（warning 色阶）。

### NotificationBell

```
🔔  3                ← 角标显示未读数
```

点击 Popover：
```
通知 (3 未读)                      [全部已读]
─────────────────────────────────────
🤖 你的 K8s skill 等待确认           5 分钟前
   K8s 故障排查 by Alice
   [查看]
─────────────────────────────────────
✅ Bob 已同意你提交的审批              2 小时前
─────────────────────────────────────
🤖 你的 Helm skill 已过期               1 天前
   30 天无人响应, 已归档
```

## 6. API（来自 T50）

| 操作 | 端点 | TanStack Query Key |
|---|---|---|
| sign | `POST /skills/:id/consent/sign` body `{channel: 'web', note?}` | mutation |
| reject | `POST /skills/:id/consent/reject` body `{channel: 'web', reason}` | mutation |
| 未读通知数 | `GET /me/notifications/unread-count` | `['notifications', 'unread-count']` |
| 通知列表 | `GET /me/notifications?limit=20` | `['notifications', 'list']` |
| 标已读 | `POST /me/notifications/:id/read` 或 `POST /me/notifications/read-all` | mutation |

## 7. 必备状态（DoD）
- [ ] Skill 详情页 status='pending_contributor_consent' 时 banner 自动显示
- [ ] 仅当前用户 user_id ∈ consent_required_from 时 sign/reject 按钮可见
- [ ] reject 强制 ≥ 5 字符理由，否则按钮 disabled
- [ ] sign 后 banner 变成 "你已同意 · 等待 N 位 contributor"
- [ ] 全员签后 banner 消失，页面顶部状态变 "草稿待审"
- [ ] NotificationBell 角标实时更新（SSE）
- [ ] 通知列表分页 (20/页)
- [ ] IM DM 跳过来 `?action=sign` → 自动打开 ConsentDialog
- [ ] tsc/lint 零警告

## 8. 验收
- [ ] 单测 ≥ 8 case：banner 渲染条件 / 按钮可见性 / reject 字符校验 / SSE 事件 reducer
- [ ] 浏览器：3 contributor 模拟 → 全员签 → banner 消失 → status 跳 draft
- [ ] 浏览器：1 contributor reject → banner 变红 "已被 X 拒绝" → reject 后页面不再可签
- [ ] SSE 断网重连测试（refresh 仍能拉最新状态）
- [ ] mobile width (375px) banner 不溢出（按钮自动 wrap）

## 9. 已知陷阱
- IM DM 跳过来的 `?action=sign` query：mount 时直接 open dialog，但要先 fetch skill 状态确认仍 pending
- 二次确认 dialog 不要太多 friction（1 个 confirm 即可）；reject 才需要 reason
- SSE 订阅必须按 user_id 路由（不能用 project_id），避免泄漏其他人的 consent
- "已读"语义：进入 Skill 详情页查看 ≠ 同意，要显式按钮才标 read
- mobile mention 跳链接（飞书内置浏览器）的 UA 可能识别错，做兼容
- NotificationBell 长连接断了用 polling 兜底（30s 一次拉 unread-count）

## 10. Claude Code 指令
顺序：`ConsentPending` 静态版（用 mock data） → `ConsentDialog` 二次确认（mutation 接通） → SSE hook → `NotificationBell` + List → mount 时处理 `?action=` query。最后跑 mobile + 多 contributor 集成。
