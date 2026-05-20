# T06 · 文档生成结果页 (核心,**最复杂**)

## 1. 目标
**产品的核心卖点屏幕**。用户看到 AI 生成的文档,可以读、改、查证据、重新生成章节。三栏布局:左侧大纲 / 中间正文 / 右侧操作。
PRD: §4.2 旅程 B,§5.3-5.4 模块 C/D,§8.2 关键交互 · 文档生成结果页

## 2. 路由
- 路径: `/projects/:id/documents/:docId`
- 入口: T05 文档列表点击卡片
- 出口: 章节内可触发 T07(证据)/ T08(重生成)/ 顶部触发 T09(提交审批)

## 3. 视觉参考
`docs/mockups/T06-document-page.html` · **像素级精雕,3 周 sprint 里这屏单独留 1.5 天**

## 4. API

| 操作 | 端点 |
|---|---|
| 加载文档 | `GET /api/v1/assets/{asset_id}` |
| 更新章节 | `PATCH /api/v1/assets/{asset_id}/chapters/{chapter_id}` body `{content_md}` |
| 重生成章节 | `POST /api/v1/assets/{asset_id}/chapters/{chapter_id}/regenerate` body `{instruction, model}` |
| 提交审批 | `POST /api/v1/assets/{asset_id}/submit` |
| 章节证据 | `GET /api/v1/assets/{asset_id}/chapters/{chapter_id}/evidence` |

## 5. 组件分解

```
src/features/documents/
├── DocumentPage.tsx              ← 三栏布局
├── components/
│   ├── DocOutline.tsx            ← 左侧大纲(锚点导航)
│   ├── DocEditor.tsx             ← 中间 TipTap 富文本
│   ├── ChapterBlock.tsx          ← 章节容器(标题 + TipTap + footer)
│   ├── ChapterFooter.tsx         ← 重生成/证据/批注 操作栏
│   ├── InlineEvidence.tsx        ← 内联证据角标 [3]
│   ├── DocSidebar.tsx            ← 右侧:文档元数据 / 状态 / 操作
│   └── DocHeader.tsx             ← 顶部:标题 / 状态 / 提交审批
└── hooks/
    ├── useDocument.ts
    ├── useChapterMutation.ts
    └── useAutoSave.ts            ← 编辑 debounce 2s 自动保存
```

TipTap 配置: `StarterKit` + `Link` + `Placeholder` + 自定义 `Evidence` mark(用 `data-evidence-id` 标注证据角标)

shadcn 用: `Button` `Card` `Separator` `Tooltip` `DropdownMenu` `Sheet` `Skeleton` `ScrollArea`

## 6. 状态管理

- 文档主数据:TanStack Query
- 编辑中草稿:`useAutoSave` 内部 useState + debounce 2s → PATCH
- 当前激活章节(滚动联动):useState + IntersectionObserver
- 抽屉(T07 证据)开关:Zustand `documentUiStore` 跨组件用

## 7. 必备状态

- [ ] Loading: 整页骨架(大纲占位 + 章节 3 个 skeleton 卡)
- [ ] Empty: 不适用(进来必有数据)
- [ ] Error: 整页错误 + 返回列表
- [ ] Saving: 顶部显示"保存中..." → "已保存 X 秒前"
- [ ] 重生成中: 章节灰化 + Progress 条覆盖

## 8. 验收

- [ ] 三栏: 左 240px 大纲 / 中自适应 / 右 320px 侧栏
- [ ] 大纲点击 → 平滑滚动 + 当前章节高亮(IntersectionObserver)
- [ ] 章节滚动到中间区域时,左侧大纲对应项高亮
- [ ] 章节标题用 font-content text-h2,正文用 font-content text-body-lg
- [ ] 内联证据 `[3]` 是橙色 chip,点击 → 触发 T07 抽屉打开,定位到证据 3
- [ ] 每章 footer 有: 重生成(→ T08)/ 查看证据(→ T07)/ 批注
- [ ] 编辑停 2s 自动保存,顶部状态从"编辑中"→"保存中"→"已保存"
- [ ] 保存失败时 toast + 不丢草稿(本地保留)
- [ ] 顶部"提交审批"按钮:状态=draft 时显示,点击 → 确认 dialog → POST submit → 跳 T09
- [ ] 文档状态徽标 + 模型来源徽标(GPT-4 / Claude-3.5)

## 9. 已知陷阱

- **TipTap 的 SSR**: Vite 没事,但要确保 editor 实例在 useEffect 里销毁
- 自动保存要避免和"重生成"冲突:重生成期间 disable 编辑
- 证据角标点击不要让 TipTap 误以为是文本编辑(用 `event.stopPropagation`)
- 三栏总宽超过 1280 时,大纲收成 icon-only;1024 以下整个右栏移到顶部 collapsible
- 长文档(>20 章)左侧大纲要有自己的 ScrollArea

## 10. Claude Code 指令
**这屏分 3 个 sub-task 做**:
1. 三栏布局 + 大纲 + 静态章节渲染(用 markdown-it 先不上 TipTap)
2. 接入 TipTap + 自动保存
3. 接入证据/重生成入口(留 callback,T07/T08 任务包里再接)
