# T35 · 前端：首次启用引导向导

## 1. 目标
用户第一次访问 "自动触发" Tab 时弹出引导，推荐勾选 3-4 条预置规则，一键启用。
Proposal: 体验要素 #35 / §7.4 AT-D.5

## 2. 路由
- 触发：访问 `/projects/:id/settings?tab=auto-triggers` 且当前用户在该项目下没启用过任何规则时弹 Dialog
- 入口：自动弹 / 也可从 AutoTriggersTab 的 EmptyState 手动触发
- 出口：完成引导后回到 Tab 看到刚启用的规则；或"跳过"关闭 Dialog

## 3. 视觉参考
- 大型 Dialog 居中显示
- 4 条规则卡片 + 复选框
- 风格沿用现有 GenerateDocDialog（v0.2 / v0.3）

## 4. API（来自 T32）

| 操作 | 端点 |
|---|---|
| 引导预览 | `GET /api/projects/{pid}/auto-triggers/onboarding` 返回 default_rules |
| 一键启用 | `POST .../onboarding` body `{ enabled_rule_ids: [...] }` |

## 5. 组件分解

```
src/features/auto-triggers/onboarding/
├── OnboardingDialog.tsx              ← 主 Dialog
├── components/
│   ├── DefaultRuleCard.tsx           ← 每条预置规则一张卡：图标 + 名称 + 描述 + 复选框
│   ├── DefaultRuleList.tsx
│   ├── EnableButton.tsx
│   └── SkipLink.tsx
└── hooks/
    ├── useOnboarding.ts              ← GET 预览
    └── useEnableRules.ts             ← POST 启用
```

shadcn 用: `Dialog` `Checkbox` `Card` `Button` `Badge`

## 6. 状态管理
- 4 条规则的勾选状态：useState（默认值由 API 提供的 default_enabled 决定）
- "首次访问"判定：本地 localStorage flag `auto_trigger_onboarding_seen_{pid}` + 后端校验"项目级是否已有规则"
- 完成后 invalidate `['auto-trigger', pid, 'rules']` 让 T33 列表刷新

## 7. 必备状态（DoD）
- [ ] Loading: 4 条规则卡片骨架
- [ ] Empty: 不会出现（API 必返 ≥ 4 条预置）
- [ ] Error: 提示"获取预置规则失败"+ 重试
- [ ] Success: 4 条卡片渲染 + 复选框默认勾选状态正确（周报 ✅ / book ⏸ 等）
- [ ] 点"启用选中"后 → mutation → 成功 toast + Dialog 关闭

## 8. 验收
- [ ] 新项目（没启用过规则）首次访问 Tab → 自动弹出
- [ ] 已启用过的项目访问 → 不弹（已读 localStorage flag）
- [ ] "跳过"按钮：不写后端，仅设 localStorage flag，下次不再弹
- [ ] 一键启用 4 条选中规则 → list 视图（T33）立即看到 4 行 enabled
- [ ] 每条规则卡片展示：图标 / 名称 / 简短描述 / 触发条件 plain English 翻译（不显示 JSON）
- [ ] 颜色用 token；tsc / lint 零警告
- [ ] 1280px 横向不溢出

## 9. 已知陷阱
- 触发条件的"plain English 翻译"由前端做（如 `cron 0 9 * * 1` → "每周一上午 9 点"）；不要后端给翻译字符串
- 默认勾选状态：周报 / PR ADR / Incident 三条勾，book 不勾（token 用量大警示）
- localStorage flag 单 user × 单 project，迁移到新机器会再次弹出（可接受）
- 用户点 Skip 后，EmptyState（T33）要显示"你跳过了引导，点这里重新打开"
- Mutation 失败时要保留勾选状态，让用户重试

## 10. Claude Code 指令
顺序：DefaultRuleCard / SkipLink（纯展示）→ useOnboarding hook → OnboardingDialog 组装 → 在 AutoTriggersTab 加挂载逻辑（条件渲染）。"plain English 翻译"提取成 utils 函数，方便复用。
