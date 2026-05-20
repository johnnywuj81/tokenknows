# T04 · 事件详情面板

## 1. 目标
点击工作台事件流的某一条,弹出右侧面板看详情:时间轴 / 元数据 / 关联文档。
PRD: §5.2 模块 B · 高价值内容识别

## 2. 路由
不是独立页,是 query string driven 的 drawer:`/projects/:id?event=:eventId`
关闭 drawer 时清掉 query。

## 3. 视觉参考
`docs/mockups/T04-event-detail.html` · 右侧 480px 抽屉

## 4. API

| 操作 | 端点 |
|---|---|
| 事件详情 | `GET /api/v1/projects/{id}/events/{event_id}` |

## 5. 组件分解

```
src/features/events/
├── EventDetailDrawer.tsx          ← shadcn Drawer 包装
├── components/
│   ├── EventHeader.tsx            ← 来源 icon + 标题 + 时间
│   ├── EventTimeline.tsx          ← 上下文事件时间轴
│   ├── EventMetadata.tsx          ← author / source / repo / branch / 文件数
│   └── EventValueScore.tsx        ← AI 评分(高价值标记)
└── hooks/
    └── useEvent.ts
```

shadcn 用: `Sheet` (右侧 drawer) / `Avatar` `Badge` `Separator` `Tabs`

## 6. 状态管理

- query param `?event=` 驱动 drawer 开关
- TanStack Query 缓存事件详情

## 7. 必备状态

- [ ] Loading: drawer 打开但内容是骨架屏
- [ ] Empty: 不适用
- [ ] Error: 显示错误 + 关闭按钮 + 重试
- [ ] Success: 完整渲染

## 8. 验收

- [ ] Drawer 滑入动画(transition-duration:DEFAULT)
- [ ] Esc / 点遮罩 / 右上 X / `?event=` 删除 都能关
- [ ] 时间轴显示前后 5 条相关事件,可点击切换 drawer 内容(不重新打开 drawer)
- [ ] 元数据栏: 来源 / 作者 / 时间 / repo / branch / 高价值标记
- [ ] "跳转生成文档"按钮:如果该事件已被纳入生成,跳到对应文档 + 锚点
- [ ] 桌面端: 480px 抽屉 + 半透明遮罩;不挡左侧导航

## 9. 已知陷阱

- 同一 drawer 切换不同 event 时,不要先关闭再打开 — 直接换内容
- 时间轴上的事件如果是 chat 类型,要做长文本截断 + 点击展开
- 一些 source(如 Cursor 私信对话)有隐私字段,不展示原文,只展示摘要

## 10. Claude Code 指令
Drawer 复用工程通用 shadcn Sheet,不要重新封装。
