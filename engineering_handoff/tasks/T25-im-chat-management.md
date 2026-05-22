# T25 · 前端：群列表选择 + 邀请 Bot + 统计仪表板

## 1. 目标
授权后让用户能"选群、邀请 bot 入群、看蒸馏统计"。是 v0.3.0 用户旅程的高潮部分（蒸馏可见）。
Proposal: §6.1 旅程 A · 步骤 5-9 / 体验要素 #25 #27

## 2. 路由
- 路径: `/projects/:id/datasources/im/connections/:cid/chats`
- 入口: T24 的连接卡片点"管理群"
- 出口: 单个 chat 详情（"返回连接列表" 或继续点"查看蒸馏结果"跳 MVP Skills 页）

## 3. 视觉参考
- 新增 mockup: `docs/mockups/T25-im-chats.html`（待补）
- 参考 MVP T05 的列表风格 + T03 工作台的统计卡片

## 4. API（来自 T23）

| 操作 | 端点 | Query Key |
|---|---|---|
| 列出可见群 | `GET .../chats?status=available,active,paused` | `['im', cid, 'chats']` |
| 邀请 bot 入群 | `POST .../chats/{platform_chat_id}/join` | mutation |
| 踢 bot | `POST .../chats/{chat_id}/leave` | mutation |
| 群统计 | `GET /api/.../im/chats/{chat_id}/stats` | `['im', 'chat', chat_id, 'stats']` |
| SignalGate 阈值 | `GET/PATCH .../im/signal/config` | `['im', cid, 'signal-config']` |
| SSE | `im.message.received` / `im.signal.computed` | 用 useSSE hook |

## 5. 组件分解

```
src/features/datasources/im/chats/
├── IMChatsPage.tsx              ← 主页：左侧群列表 + 右侧详情
├── components/
│   ├── ChatList.tsx
│   ├── ChatListItem.tsx         ← 名称 + 成员数 + 30天消息数 + status badge
│   ├── ChatDetailPanel.tsx      ← 右侧详情，含统计 + signalgate 配置 + 操作
│   ├── ChatStats.tsx            ← 4 个数字卡片：消息/Signal/段/Skill
│   ├── SignalRateChart.tsx      ← 7 天信号率折线（recharts）
│   ├── DroppedKeptPie.tsx       ← 噪声过滤可视化（要素 #25）
│   ├── TopContributors.tsx      ← TOP-5 贡献者（要素 #27）
│   ├── SignalGateConfig.tsx     ← 阈值 slider（0.2 / 0.4 / 0.6 三档）
│   └── InviteBotButton.tsx      ← 邀请 bot 入群（含飞书引导提示）
└── hooks/
    ├── useChats.ts
    ├── useChatStats.ts
    ├── useInviteBot.ts
    └── useSignalConfig.ts
```

shadcn 用: `Card` `Badge` `Slider` `Tooltip` `Skeleton` `Tabs` `Button` `Avatar`
recharts: `LineChart` `PieChart`

## 6. 状态管理

- 群列表 + 统计 + 配置: 全部 TanStack Query
- 选中的 chat_id: useState（在 IMChatsPage 顶层）
- SSE 推送进来的新消息计数：用 `setQueryData` 增量更新统计卡片，不要全量 refetch

## 7. 必备状态（DoD）
- [ ] Loading: 左侧列表骨架 + 右侧统计骨架
- [ ] Empty: "授权成功，飞书账号下没找到可监听的群" + 帮助链接
- [ ] Error: 重试
- [ ] Success: 列表 + 统计 + 配置都对
- [ ] InviteBotButton 点击 → 调用 join → 显示"邀请请求已发出，bot 入群后此卡片状态变更"
- [ ] SignalGate slider 变更 → 防抖 1s 后 PATCH → toast 提示"已保存，新阈值即时生效；如需重算历史，点 [重新计算]"

## 8. 验收
- [ ] 群列表按 status 分组：active / paused / available / removed
- [ ] 群成员数 + 30 天消息数显示正确
- [ ] 信号率折线图至少有 7 个数据点（最近 7 天）
- [ ] DroppedKeptPie 显示规则过滤 / LLM 过滤 / 保留 三色分布（要素 #25）
- [ ] TopContributors 显示头像 + 名字 + 消息数 + 蒸馏段数（要素 #27）
- [ ] 邀请 bot 入群：飞书原生确认弹窗能拉起；失败显示具体原因
- [ ] SignalGate slider 三档手动测试覆盖
- [ ] 拖动 slider → mutation → 列表统计 5s 内更新
- [ ] 切换不同 chat 时右侧详情立即切换
- [ ] tsc / lint 零警告
- [ ] 1280px 横向不溢出

## 9. 已知陷阱
- 邀请 bot 入群是异步事件，前端要 poll chat status；建议 SSE `im.chat.bot_joined`
- 飞书的 chat 列表可能有上百个；做虚拟列表（react-window）或分页（v0.3.0 先简单分页 20/页）
- ChatStats 的数字从 redis 缓存来，缓存 TTL 5 分钟；用户点 "强制刷新" 走 ?force=true
- 30 天滑动窗口的 0 点切换会有 1-5 分钟数据轻微跳变，UI 不必特别处理
- 重新计算（recompute）触发后是后台任务，前端 toast + 进度条；不要阻塞用户
- 群名可能含 emoji / 特殊字符，列表渲染要支持

## 10. Claude Code 指令
按"自下而上"：先 ChatStats / DroppedKeptPie / TopContributors / SignalRateChart 这种纯展示组件做完 → SignalGateConfig（有 mutation） → ChatList → IMChatsPage 组装。SSE 接入留到最后，先用 query polling 测一遍逻辑通了再换。
