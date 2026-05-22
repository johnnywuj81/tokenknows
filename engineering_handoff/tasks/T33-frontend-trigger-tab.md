# T33 · 前端：项目设置"自动触发"Tab + 列表 + 启停 toggle

## 1. 目标
在项目设置页加"自动触发"Tab，展示所有规则的状态 / 触发条件 / 30 天产出 + 启停开关。
Proposal: §7.4 AT-D / 体验要素 #29

## 2. 路由
- 路径: `/projects/:id/settings?tab=auto-triggers`
- 入口: ProjectSettingsPage 左侧 sub-nav 加"自动触发"
- 出口: 切换其他 Tab / 点详情进入抽屉

## 3. 视觉参考
- 沿用 ProjectSettingsPage 现有 Tab 风格（与"成员 / 数据源 / 出域"并列）
- 列表行参考 DocumentCard 视觉密度

## 4. API（来自 T32）

| 操作 | 端点 | TanStack Query Key |
|---|---|---|
| 列规则 | `GET .../auto-triggers/rules` | `['auto-trigger', pid, 'rules']` |
| 启停（PATCH enabled） | `PATCH .../rules/{rid}` | mutation |
| 规则详情 | `GET .../rules/{rid}` | `['auto-trigger', 'rule', rid]` |
| 触发历史 | `GET .../executions?rule_id=...` | `['auto-trigger', 'rule', rid, 'executions']` |
| 引导预览 | `GET .../onboarding` | `['auto-trigger', pid, 'onboarding']` |

## 5. 组件分解

```
src/features/settings/auto-triggers/
├── AutoTriggersTab.tsx        ← Tab 主入口
├── components/
│   ├── RuleList.tsx
│   ├── RuleListItem.tsx       ← 一行: 状态 / 名称 / 模式 / 触发条件 / 最近触发 / 30天产出 / 操作
│   ├── RuleDetailDrawer.tsx   ← 详情抽屉（v0.4.0 只读）
│   ├── RuleStatusBadge.tsx    ← enabled / paused
│   ├── ModeBadge.tsx          ← cron / event / threshold
│   └── EmptyState.tsx         ← 还没启用规则时显示
└── hooks/
    ├── useRules.ts
    ├── useToggleRule.ts
    └── useRuleExecutions.ts
```

shadcn 用: `Card` `Switch` `Sheet`(详情抽屉) `Badge` `Button` `Tooltip`

## 6. 状态管理
- 列表 + 详情: TanStack Query
- Switch 启停: optimistic update + mutation
- 抽屉 open/close: useState

## 7. 必备状态（DoD）
- [ ] Loading: 列表骨架
- [ ] Empty: "还没启用自动触发规则" + "去引导向导"CTA（跳 T35）
- [ ] Error: 重试
- [ ] Success: 列表显示规则 + 启停状态正确
- [ ] Switch 点击立即 optimistic update + 后台 PATCH，失败回滚 + toast

## 8. 验收
- [ ] 列表显示 v0.4.0 默认启用的"周一周报"规则
- [ ] 关闭"周一周报"规则后周一上午不再触发（实测）
- [ ] 详情抽屉显示规则原理 / 触发条件 / 频率限制 / 最近 20 次触发历史
- [ ] 30 天产出列正确（join trigger_execution 计数）
- [ ] 切换 Tab 不丢失抽屉状态
- [ ] tsc / lint 零警告

## 9. 已知陷阱
- 启停的 mutation 失败时要回滚 Switch 状态（optimistic update 风险）
- 抽屉里 "最近 20 次触发" 别用一次 query 加载全部历史；用 query key `[rule_id, 'executions', { limit: 20 }]` 单独 fetch
- 项目级规则和实例级默认规则混在一起显示时要区分（badge："默认 / 自定义"）
- ProjectSettingsPage 现有 Tab 切换用 URL ?tab= query，新增 Tab 要保持一致

## 10. Claude Code 指令
按"自下而上"：RuleListItem / RuleStatusBadge / ModeBadge（纯展示）→ useRules → RuleList → AutoTriggersTab → RuleDetailDrawer。先用 MSW mock 数据测通 UI，再连真后端。
