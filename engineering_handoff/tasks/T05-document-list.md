# T05 · 文档列表

## 1. 目标
项目内所有"生成 / 编辑中 / 待审 / 已发布"的文档总览,支持分类筛选。
PRD: §5.3 模块 C · 文档自动生成

## 2. 路由
- 路径: `/projects/:id/documents`
- 入口: 工作台侧栏 "文档"
- 出口: 点击文档卡 → T06 文档结果页

## 3. 视觉参考
`docs/mockups/T05-document-list.html`

## 4. API

| 操作 | 端点 | Query Key |
|---|---|---|
| 文档列表 | `GET /api/v1/projects/{id}/assets?type=&status=` | `['assets', projectId, filters]` |
| 触发新生成 | `POST /api/v1/projects/{id}/assets/generate` | (mutation) |

## 5. 组件分解

```
src/features/documents/
├── DocumentListPage.tsx
├── components/
│   ├── DocumentCard.tsx           ← 卡片:类型 icon / 标题 / 状态 / 更新时间
│   ├── DocumentFilters.tsx        ← Tabs: 全部 / 草稿 / 待审 / 已发布
│   ├── DocumentTypeFilter.tsx     ← 类型: 周报 / 月报 / 技术博客 / API 文档
│   └── GenerateDocButton.tsx      ← 触发新生成的入口按钮
└── hooks/
    └── useDocuments.ts
```

shadcn 用: `Card` `Tabs` `Badge` `Select` `Button` `DropdownMenu`

## 6. 状态管理

- 筛选条件: URL query string(`?status=draft&type=weekly`)
- 列表: TanStack Query,依赖 filter 作为 query key 一部分

## 7. 必备状态

- [ ] Loading: 6 个骨架卡片
- [ ] Empty: "还没有文档" + "生成第一份"按钮
- [ ] Error: 整页 ErrorState 重试
- [ ] Success: 卡片网格(3 列 desktop / 2 列 tablet)

## 8. 验收

- [ ] 状态徽标颜色: draft=warning / reviewing=info / approved=success / published=accent-primary
- [ ] 卡片显示:类型 / 标题 / 章节数 / 更新时间(date-fns formatRelative) / 作者头像
- [ ] 筛选切换走 URL,刷新页面保留状态
- [ ] "生成新文档"按钮触发对话框,选类型 + 时间范围 + 数据源
- [ ] 生成中的文档卡显示 Progress 条 + "生成中"徽标 + 不可点击
- [ ] 鼠标悬停卡片有 elev-2 阴影
- [ ] 卡片有"更多"菜单:复制 / 删除 / 导出

## 9. 已知陷阱

- 文档列表可能很多,需要分页或无限滚动;MVP 用 cursor 分页,每页 20
- "生成中"状态需要 polling 进度(每 5 秒查一次),完成后自动刷新列表
- 删除操作要二次确认 dialog,不要直接删

## 10. Claude Code 指令
卡片 / 筛选 / 列表三个组件独立可测试,先做静态卡片再接数据。
