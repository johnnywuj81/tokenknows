# T07 · 证据链抽屉

## 1. 目标
点击文档内的证据角标 [n] 弹出右侧抽屉,展示这条证据的来源(commit / PR / chat 等)和上下文。
PRD: §5.4 模块 D · 证据链与来源追溯,§8.3 关键交互 · 证据链查看

## 2. 路由
不是独立路由,是 T06 文档页内的 drawer。可选 URL `?evidence=:id` 用于深链。

## 3. 视觉参考
`docs/mockups/T07-evidence-drawer.html` · 右侧 480px 抽屉,与 T04 类似但内容不同

## 4. API

| 操作 | 端点 |
|---|---|
| 证据详情 | `GET /api/v1/evidence/{evidence_id}`(或包在章节证据接口里) |
| 章节所有证据 | `GET /api/v1/assets/{asset_id}/chapters/{chapter_id}/evidence` |

## 5. 组件分解

```
src/features/evidence/
├── EvidenceDrawer.tsx
├── components/
│   ├── EvidenceHeader.tsx
│   ├── EvidenceSourceCard.tsx     ← 显示原始事件信息 + 链接到 T04
│   ├── EvidenceQuote.tsx          ← 引用的原文(高亮匹配片段)
│   ├── EvidenceContext.tsx        ← 上下文(前后段落/对话)
│   └── EvidenceListPanel.tsx      ← 抽屉顶部:本章所有证据列表(可切换)
└── hooks/
    └── useEvidence.ts
```

shadcn 用: `Sheet` `Tabs` `Card` `Badge` `Separator`

## 6. 状态管理

- 当前激活证据 ID: Zustand `documentUiStore.activeEvidenceId`(T06 也用)
- 抽屉开关: Zustand `documentUiStore.evidenceOpen`

## 7. 必备状态

- [ ] Loading: 抽屉内骨架
- [ ] Empty: 章节没有证据 → 友好提示
- [ ] Error: 重试
- [ ] Success: 完整渲染

## 8. 验收

- [ ] 抽屉顶部显示本章所有证据列表,当前激活项高亮
- [ ] 切换证据不重新打开 drawer
- [ ] 引用原文高亮匹配片段(用 `<mark>` 包)
- [ ] 上下文展示前 / 后各 3 行,可"显示更多"
- [ ] 点"跳转源事件"→ 在 T04 drawer 里打开该事件(或新页签)
- [ ] 桌面 480px,移动端全屏

## 9. 已知陷阱

- 证据上下文可能很长,要截断 + 展开
- 一条证据可能引用 chat 对话,要保留发送者头像 / 时间戳
- 证据来源是隐私敏感内容时,不展示原文(后端字段 `is_private: true`),只显示摘要 + "源已脱敏"标记

## 10. Claude Code 指令
和 T06 的 documentUiStore 共享状态,不要新建 store。
