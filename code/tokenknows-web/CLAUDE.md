# TokenKnows MVP — Claude Code 项目记忆

> 这个文件是 Claude Code 在本仓库工作时的全局上下文。Solo 开发者 + AI 协作模式。

## 项目一句话

把研发过程(代码、PR、聊天、文档)自动汇聚成"项目知识资产"的私有化平台。MVP 重点是"研发事件 → 文档 → 证据链 → 发布"的闭环。

## 技术栈

- **前端**(本仓库): React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + shadcn/ui
- **状态**: Zustand(client state) + TanStack Query(server state)
- **路由**: React Router v7(API 与 v6 兼容,`createBrowserRouter` 直接用)
- **表单**: react-hook-form + zod
- **富文本**: TipTap v3 (T06 文档结果页)
- **Mock 后端**: MSW (开发阶段全程用)
- **后端**(另一仓库): Python 3.11 + FastAPI + Postgres 15 (pgvector + tsvector) + Redis + S3/MinIO

## 必读文档(按需读)

- `docs/PRD.md` — 产品需求、用户旅程、验收标准
- `docs/TDD.md` — 后端 API 端点、数据 schema、架构(§6 是 API 大全)
- `docs/DesignHandoff.md` — 设计 token、组件清单、每屏规格(§5 各屏 quick reference)
- `docs/mockups/T0X-*.html` — 像素级视觉参考,浏览器直接打开看交互态
- `docs/engineering_handoff/tasks/` — 每屏的施工任务包

## 工作约定

### 写代码时

- 优先用 shadcn/ui 组件,不要自己造 Button/Card/Input
- shadcn 组件代码在 `src/components/ui/`,可以改;但改之前先确认是否影响其他屏
- Tailwind class 用项目自定义 token,不要用原生色:
  - ✅ `bg-bg-card text-text-primary border-border-subtle`
  - ❌ `bg-stone-50 text-stone-900 border-stone-200`
- 颜色 token 完整清单见 `docs/DesignHandoff.md` §2.1,已经写进 `tailwind.config.ts`
- **Tailwind v4 重要**:`tailwind.config.ts` 由 `src/index.css` 顶部的 `@config "../tailwind.config.ts";` 加载。不要删掉这一行。
- **React 19 重要**: 不要再用 `defaultProps` (已移除);函数组件默认参数用解构默认值即可。Server Components 在本项目不用(纯 SPA)。
- 字体: 标题用 `font-content` (Lora serif), UI 用 `font-ui` (Poppins), 代码/ID 用 `font-mono`

### 文件组织

每个业务屏一个 feature 文件夹,例如:

```
src/features/workbench/
├── WorkbenchPage.tsx       ← 路由入口
├── components/
│   ├── ProjectCard.tsx
│   ├── EventStream.tsx
│   └── TodoList.tsx
├── hooks/
│   └── useProjects.ts      ← TanStack Query
└── types.ts                ← 本 feature 的类型(API DTO 之外)
```

### API 调用

- 所有后端调用走 `src/lib/api.ts` 的 axios/fetch 客户端
- 列表 / 详情查询用 TanStack Query
- Query key 规范: `['projects']` / `['projects', id]` / `['projects', id, 'events']`
- mutation 后用 `queryClient.invalidateQueries(...)` 而不是手动 setData
- 后端 API 端点完整清单在 `docs/TDD.md` §6.1
- 任何接口在没有真后端时,先在 `src/mocks/handlers.ts` 加 MSW handler

### 状态管理

- 服务端数据:**永远用 TanStack Query**,不要塞进 Zustand
- 跨页/全局 UI 状态:Zustand(例如:当前用户、当前项目、侧边栏开合)
- 本页临时状态:useState 就行,不要过度抽象

### 必备 UI 状态(每屏都要有)

任何会调接口的组件必须有:

1. **Loading**: 用 shadcn 的 Skeleton 或 spinner;骨架优先
2. **Empty**: 用 `src/components/shared/EmptyState.tsx`,带插画/图标 + 主操作
3. **Error**: 用 `src/components/shared/ErrorState.tsx`,有"重试"按钮
4. **Success**: 数据正常展示

任务包里都会列出来,不用记。

### 提交规范

- 每完成一屏 commit 一次
- commit message 用中文,前缀 `T0X:` 例如 `T03: 工作台首页静态版本完成`
- 不要在一个 commit 里横跨多屏

## 不要做的事

- 不要引入额外的 UI 库 (antd / mui / chakra) — 全部用 shadcn
- 不要写 CSS-in-JS — Tailwind only
- 不要造 axios interceptor 之外的"API 抽象层" — 简单 fetch hooks 就够
- 不要给 ts 配 `any` — 实在不知道用 `unknown` 然后窄化
- 不要在不读 mockup HTML 的情况下"猜"视觉

## 当卡住时

- 先看任务包的"已知陷阱"段落
- 再看 mockup HTML 的源码(Tailwind class 一目了然)
- 再看 DesignHandoff 对应屏的 quick reference
- 还卡住就停下来问开发者(我),不要乱猜

## 调试速查

```bash
# 类型检查
npx tsc -b --force   # 注意: 根 tsconfig 是 solution-style, --noEmit 是空检查

# Lint
npm run lint

# 单测
npm run test

# 跑 dev,看 MSW 是否拦截了请求
npm run dev  # 然后 devtools → Network → 看 /api 请求是否 Service Worker fulfilled
```

## 推进顺序(关键!)

按 `docs/engineering_handoff/README.md` 里的 4 周 sprint 计划走。
**不要跳着做**,前置屏没完成不要开后面的(数据依赖会塌)。

完整顺序: T01 → T02 → T03 → T05 → T06 → T07 → T08 → T04 → T09 → T10 → T11 → T12 → T13 → T14 → T15。
