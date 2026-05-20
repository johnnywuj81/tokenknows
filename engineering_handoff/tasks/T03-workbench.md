# T03 · 工作台首页

## 1. 目标
用户每天打开产品看到的第一屏。三列布局:左侧项目列表、中间实时事件流、右侧本周待办。
PRD: §4.2 旅程 B,§8.1 关键交互 · 项目工作台

## 2. 路由
- 路径: `/`(已登录默认页) 和 `/projects/:id`(进入特定项目)
- `/` 显示"选择项目"或"最近项目";`/projects/:id` 显示该项目的工作台
- 入口: 登录后默认进入
- 出口: 点击项目卡 / 事件 / 待办 进入对应子页

## 3. 视觉参考
`docs/mockups/T03-workbench.html`(**整个项目最复杂的几屏之一,优先做静态版**)

## 4. API

| 操作 | 端点 | Query Key |
|---|---|---|
| 项目列表 | `GET /api/v1/projects` | `['projects']` |
| 项目详情 | `GET /api/v1/projects/{id}` | `['projects', id]` |
| 事件列表 | `GET /api/v1/projects/{id}/events?from=&to=` | `['projects', id, 'events', range]` |
| 实时事件 SSE | `GET /sse/projects/{id}/events`(MVP 可先用 polling) | (custom hook) |
| 本周待办 | 复用 `events` 接口,按 `due_at < now+7d` 过滤;或新建 `/projects/{id}/todos` |

## 5. 组件分解

```
src/features/workbench/
├── WorkbenchPage.tsx
├── components/
│   ├── ProjectSwitcher.tsx       ← 左侧:当前项目 + 切换下拉
│   ├── ProjectStats.tsx          ← 数字卡:本周事件数 / 待审文档 / 数据源健康
│   ├── EventStream.tsx           ← 中间:实时事件流(列表 + 时间分组)
│   ├── EventCard.tsx             ← 单条事件卡(commit / PR / chat 不同样式)
│   ├── EventFilter.tsx           ← 按 source_type / author 筛选
│   ├── TodoList.tsx              ← 右侧:本周待办
│   └── EmptyWorkbench.tsx        ← 项目未接入数据源时
└── hooks/
    ├── useEventStream.ts         ← 包 SSE(MVP 用 setInterval polling 30s)
    └── useProjectStats.ts
```

shadcn 用: `Card` `Badge` `Avatar` `ScrollArea` `Tabs` `Skeleton` `Tooltip`

## 6. 状态管理

- 当前项目 ID: Zustand `currentProjectStore`(切项目时所有 query key 重新跑)
- 事件流分页: `useInfiniteQuery`(按时间倒序、每页 50 条)
- SSE 接收新事件:`queryClient.setQueryData(['projects', id, 'events', ...], 旧 + 新)`

## 7. 必备状态

- [ ] Loading: 三栏分别有骨架屏(Skeleton 卡片占位)
- [ ] Empty:
  - 没项目 → 大空态 + "新建项目"按钮 → T02
  - 有项目但无事件 → 中间栏空态 + "检查数据源" → T13
- [ ] Error: 行级重试按钮,每栏独立
- [ ] Success: 事件按日期分组("今天" / "昨天" / "周三 12 月 X 日")

## 8. 验收

- [ ] 三栏布局: 左 240px / 中 自适应 / 右 320px,1280px 以上无问题
- [ ] 项目切换下拉显示 5 个最近项目 + "查看全部"
- [ ] EventCard 4 种 source 用不同 icon + 不同左侧色条:
  - commit (代码绿) / PR (品牌橙) / chat (信息蓝) / doc-edit (text-muted)
- [ ] 实时新事件用淡入动画(transition-duration:fast)
- [ ] 待办按 due_at 升序,过期项目标红
- [ ] Stats 数字带千位分隔符,鼠标悬停 Tooltip 显示明细
- [ ] 切换项目时 URL 同步(`/projects/:id`)

## 9. 已知陷阱

- **不要在第 1 周接 SSE**。用 setInterval polling 30 秒一次,代码注释 "SSE 替换点"
- 事件流可能很长(1000+ 条),用 `react-window` 虚拟滚动 或者只渲染最近 200 条 + "加载更早"按钮
- 项目切换时,如果旧项目还有 in-flight 请求,记得 `queryClient.cancelQueries`
- mockup 里的项目卡有"健康度"小圆点(绿/黄/红),后端字段是 `health: 'healthy' | 'degraded' | 'down'`

## 10. Claude Code 指令
先做纯静态版本(三栏 + 假数据),再接 MSW,最后加 polling。**SSE 留 TODO 注释**。
