# T24 · 前端：IM 数据源向导 + 连接卡片

## 1. 目标
让用户能"3 步内"完成飞书个人助理模式的接入。
Proposal: §6.1 旅程 A / §7.1 IM-A / 体验要素 #23 #24

## 2. 路由
- 路径: `/projects/:id/datasources`（在 MVP 数据源页基础上新增 IM tab）
- 入口: 工作台侧栏"数据源" → IM tab
- 出口: 授权后跳 `/projects/:id/datasources/im/connections/{cid}/chats`（T25）

## 3. 视觉参考
- 沿用 MVP 数据源页的视觉风格（卡片网格 + Tab 切换）
- 新增 mockup（待补）: `docs/mockups/T24-im-datasource.html`

## 4. API（来自 T23）

| 操作 | 端点 | TanStack Query Key |
|---|---|---|
| 列连接 | `GET /api/projects/{pid}/im/connections` | `['im', pid, 'connections']` |
| 创建（拿 authorize_url） | `POST /api/projects/{pid}/im/connections` | mutation |
| 删除（撤回） | `DELETE .../connections/{cid}` | mutation |
| 暂停/恢复 | `PATCH .../connections/{cid}` | mutation |

MSW handler: 在 v0.3.0 阶段先 mock 返回固定 authorize_url + 假状态。

## 5. 组件分解

```
src/features/datasources/im/
├── IMTabPage.tsx                ← 主入口，挂在 DatasourcePage tab
├── components/
│   ├── AddIMDialog.tsx          ← 选平台 + 选模式 + 合规说明三步弹窗
│   ├── ComplianceCard.tsx       ← 三条合规说明卡片
│   ├── IMConnectionCard.tsx     ← 单个连接的状态卡片
│   ├── ConnectionActions.tsx    ← 暂停 / 恢复 / 撤回菜单
│   └── PlatformBadge.tsx        ← 飞书/钉钉/企微图标 badge（v0.3.0 只飞书亮）
└── hooks/
    ├── useIMConnections.ts
    ├── useCreateIMConnection.ts
    └── useRevokeIMConnection.ts
```

shadcn 用: `Dialog` `Card` `Badge` `Button` `DropdownMenu` `Alert` `AlertDialog`(撤回二次确认)

## 6. 状态管理

- 列表: TanStack Query
- 添加流程: 本地 `useState` 管理"步骤指示" + Dialog open/close
- 授权回调: callback 页（已在 T18 后端处理）跳回 `/projects/:id/datasources?im_callback=success` → 前端 toast + invalidate query

## 7. 必备状态（DoD）
- [ ] Loading: 列表骨架 + 卡片骨架
- [ ] Empty: 用 EmptyState "还没有 IM 数据源，点添加开始"
- [ ] Error: 连接 status='error' 时卡片显示 red badge + "重新授权"按钮
- [ ] Success: 列表 + 各种状态正确展示
- [ ] AddIMDialog 三步：选平台 → 选模式 → 合规说明 → 跳转飞书 OAuth
- [ ] 撤回时 AlertDialog 二次确认 "撤回后 30 天内将清理所有原始消息"
- [ ] 键盘可达：Tab 顺序 + Enter 触发主操作

## 8. 验收
- [ ] AddIMDialog 三条合规说明显示正确（要素 #24）
- [ ] 钉钉 / 企业微信卡片显示"v0.3.x 即将支持"灰态，不可点
- [ ] 撤回连接后列表立即移除（optimistic update + invalidate）
- [ ] 暂停状态的连接卡片有视觉区分（灰色 + "已暂停"角标）
- [ ] 卡片上显示数据：监听群数 / 30 天消息数 / 最近同步时间
- [ ] 颜色用 token，不要 stone/gray
- [ ] tsc / lint 零警告

## 9. 已知陷阱
- 飞书 OAuth 跳转走的是新窗口还是当前窗口？v0.3.0 用当前窗口（避免弹窗拦截），授权后跳回带 query string
- 创建连接的 mutation 成功后**不要**立刻 invalidate 列表（还没授权，列表里也没新记录）；等 callback 跳回再 invalidate
- 撤回是异步的（30 天清理），UI 立即从列表移除即可，但要 toast 提示"数据将在 30 天内清理"
- Personal 模式 v0.3.0 用户 = connection 创建者，UI 隐藏"全员授权"等企业模式选项
- IM tab 切回 GitHub / Claude Code tab 时不要丢已展开的卡片状态

## 10. Claude Code 指令
按 OpenAPI 先把 hooks 写完（用 T23 生成的 client）→ ComplianceCard / PlatformBadge 这种纯展示组件 → AddIMDialog → IMConnectionCard → 接到 IMTabPage。MSW 全用 fake authorize_url（点击立刻跳转一个 dummy 页面再回来），不要真接飞书。
