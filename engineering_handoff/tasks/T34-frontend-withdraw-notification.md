# T34 · 前端：5 分钟撤回窗口通知卡 + 自动徽标 + 可解释卡

## 1. 目标
让用户在自动触发的关键节点（撤回窗口、生成完成、误触发反馈）有清晰的 UI 反馈。
Proposal: 体验要素 #30 / #33 / #34

## 2. 路由
本任务不新增路由。增强的位置：
- 全局：撤回窗口通知卡（右下浮动，类似 toast）
- DocumentPage 顶部：自动生成 asset 显示"自动触发"徽标 + 可解释卡

## 3. 视觉参考
- 通知卡：参考 sonner toast 但更结构化（含倒计时 + "取消"按钮）
- 自动徽标：DocHeader 顶部状态 badge 旁加 🤖 图标 + tooltip
- 可解释卡：DocHeader 下方可展开 panel，类似自评卡风格

## 4. API（来自 T32）

| 操作 | 端点 / 来源 |
|---|---|
| 订阅 SSE 事件 | EventSource（auto_trigger.scheduled / fired / canceled / failed） |
| 撤回执行 | `POST /api/projects/{pid}/auto-triggers/executions/{eid}/cancel` |
| 报告误触发 | `POST .../executions/{eid}/flag-false-positive` |
| 执行详情（可解释卡用）| `GET .../executions/{eid}` |

## 5. 组件分解

```
src/features/auto-triggers/
├── WithdrawNotification.tsx          ← 右下浮动卡，监听 SSE
├── components/
│   ├── CountdownTimer.tsx            ← 显示剩余 5 分钟倒计时
│   ├── TriggerExplainCard.tsx        ← DocumentPage 下方可展开
│   ├── AutoTriggerBadge.tsx          ← DocHeader 上的 🤖 徽标
│   └── FalsePositiveDialog.tsx       ← "报告误触发"二次确认
└── hooks/
    ├── useTriggerSSE.ts              ← 订阅 auto_trigger.* 事件
    ├── useCancelExecution.ts
    └── useFlagFalsePositive.ts

src/features/documents/page/components/DocHeader.tsx
  ← 加 AutoTriggerBadge 显示 (asset.trigger_meta 不为空时)

src/features/documents/DocumentPage.tsx
  ← 加 TriggerExplainCard 挂在 DocHeader 下方
```

shadcn 用: `Card` `Button` `AlertDialog`（误触发确认）`Progress`（倒计时）

## 6. 状态管理
- SSE 监听全局挂在 AppLayout 上方，事件分发到对应通知 UI
- 倒计时用 useEffect setInterval（每秒减一），到 0 时 unmount
- TriggerExplainCard open/close 用 useState；默认 collapsed

## 7. 必备状态（DoD）
- [ ] 收到 SSE `auto_trigger.scheduled` 事件 → 右下角浮出通知卡 + 5 分钟倒计时
- [ ] 用户点"取消" → 调 cancel API → 通知卡变红"已取消"3 秒后消失
- [ ] 5 分钟到 → 通知卡变绿"已生成" + 链接到新 asset
- [ ] DocumentPage 打开有 trigger_meta 的 asset → DocHeader 上 🤖 徽标 + 下方可展开 TriggerExplainCard
- [ ] 误触发对话框 ≥ 2 字符理由才允许提交

## 8. 验收
- [ ] 用 MSW 模拟 SSE 事件 → 通知卡正确出现
- [ ] 倒计时精确到秒，最后 1 分钟变红色提示
- [ ] 同时多份待生成 → 通知卡聚合（"5 分钟后将生成 3 份文档" + 展开列表）
- [ ] 可解释卡显示完整 signal：触发模式 / 规则名 / 信号摘要 / confidence
- [ ] 颜色用 token，无原生 stone/gray
- [ ] tsc / lint 零警告

## 9. 已知陷阱
- SSE 在 Safari 长连有问题（v0.2 已知 incident），用 EventSourcePolyfill 兜底
- 多个 scheduled 事件并行到达时不要刷屏，按 fire_at 排序聚合，最多显示 1 张聚合卡
- 用户切换页面后 SSE 断开重连 → 重连时拉取最近 5 分钟内的 scheduled execution 重建通知卡（防止漏 toast）
- TriggerExplainCard 显示在 DocHeader 下，但 BookProgressCard（v0.2）也在那个位置，要协调 z-index 和挂载顺序
- AutoTriggerBadge 用 lucide `Bot` 图标，避免和 v0.3 IM 接入的图标冲突

## 10. Claude Code 指令
顺序：CountdownTimer 单独写 + 单测时间精度 → AutoTriggerBadge / TriggerExplainCard（纯展示）→ useTriggerSSE → WithdrawNotification 组装。Polyfill EventSource 在 main.tsx 引入。
