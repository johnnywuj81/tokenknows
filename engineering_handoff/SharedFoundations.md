# SharedFoundations · TokenKnows 前端项目地基

> **定位**：T01 之前必须落地的项目地基。15 个任务（T01–T15）共享的基础设施层。**一次写完、反复引用**，避免每个任务都重新决策。
>
> | 项 | 内容 |
> |---|---|
> | 版本 | v0.1 |
> | 撰写日期 | 2026-05-20 |
> | 上游 | [Architecture.md](./Architecture.md) §2/§10（宏观分层 + 任务-feature 映射）|
> | 下游 | [TaskTechDesign.md](./TaskTechDesign.md) Part 2（每屏深化时引用本文节号）|
> | 阅读顺序 | §1 → §2 → §4 → §5 → §7 → §8 → 其它按需 |

---

## 1. 项目代码地图

`/Users/wujun/TokenKnows/code/tokenknows-web/src/`

```
src/
├── main.tsx                   ✅ 已 bootstrap (QueryClient + RouterProvider + MSW)
├── App.tsx                    ✅ token 验证页（用作 / 路由前的占位）
├── index.css                  ⚠️ 有 bug（§8 必修：重复 :root 覆盖 tokens.css 的 mapping）
├── routes/
│   └── index.tsx              ✅ 完整 15 路由占位表
├── styles/
│   └── tokens.css             ✅ SSOT — CSS 变量 + shadcn 兼容 mapping
├── lib/
│   ├── utils.ts               ✅ cn() 已有
│   └── api.ts                 ❌ §2 待建
├── components/
│   ├── ui/                    ✅ 21 个 shadcn 组件已生成
│   └── shared/
│       ├── EmptyState.tsx     ❌ §3 待建（T03/T05/T10 阻塞）
│       ├── ErrorState.tsx     ❌ §3 待建（全屏阻塞）
│       └── LoadingSkeleton.tsx ❌ §3 待建（全屏阻塞）
├── stores/                    ❌ §4 待建
│   ├── authStore.ts             （T01-T15 全用）
│   ├── projectStore.ts          （T03 之后全用）
│   ├── uiStore.ts               （drawer/sheet 开合）
│   └── documentUiStore.ts       （T06/T07/T08 共用）
├── features/                  ✅ 13 个空目录已建（按任务包域命名）
│   ├── admin/ auth/ documents/ events/ evidence/ generation/
│   ├── projects/ publish/ redaction/ review/ settings/ workbench/
├── mocks/
│   ├── browser.ts             ✅ MSW worker 已建
│   ├── handlers.ts            ⚠️ 内容空，§6 待建
│   └── fixtures/              ❌ §6 待建
├── types/                     ❌ §1 立刻补 api.ts → DTO
│   └── api.ts                   （后端 schemas/api 镜像）
└── assets/                    ✅ hero/vite 资源
```

**Owner 责任**：solo 模式下全部是你；多人入场时 `features/*` 按任务分人即可，`stores/` `lib/` `components/shared/` 维持 1 人主修以免冲突。

---

## 2. `src/lib/api.ts` 设计

### 2.1 骨架

```typescript
// src/lib/api.ts
import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/authStore'

export interface ApiResponse<T> {
  data: T
}

export interface ApiError {
  code: string          // 归一化错误码（见 §2.3 表）
  message: string       // 给用户看
  detail?: unknown      // 给开发者看
  status: number        // HTTP 状态
}

export const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// Request: 注入 Authorization
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response: 错误归一 + 401 自动跳登录
api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const apiErr = normalizeError(error)

    if (apiErr.status === 401 && !window.location.pathname.startsWith('/login')) {
      useAuthStore.getState().logout()
      const redirect = window.location.pathname + window.location.search
      window.location.href = `/login?redirect=${encodeURIComponent(redirect)}`
      return Promise.reject(apiErr)
    }

    return Promise.reject(apiErr)
  },
)

function normalizeError(error: AxiosError<{ detail?: string; code?: string }>): ApiError {
  const status = error.response?.status ?? 0
  const code = error.response?.data?.code ?? mapStatusToCode(status)
  const message = error.response?.data?.detail ?? defaultMessage(code)
  return { code, message, detail: error.response?.data, status }
}
```

### 2.2 何时用 axios / 何时手写 fetch

**所有业务调用必须走 `api`**。SSE 例外：用原生 `EventSource` 而非 axios（axios 不支持 server-sent events）。具体见 §5.4。

### 2.3 错误码归一表

| HTTP | code | 默认 toast | 处理 |
|---|---|---|---|
| 400 | `BAD_REQUEST` | "请求参数有误" | 行级显示 detail.message |
| 401 | `UNAUTHORIZED` | （静默） | 自动 logout + redirect 到 /login |
| 403 | `FORBIDDEN` | "无权访问" | 跳 / 或显示 ErrorState |
| 404 | `NOT_FOUND` | "资源不存在" | 跳列表或 404 页 |
| 409 | `CONFLICT` | "资源冲突，请刷新" | 弹 dialog（如项目名重复） |
| 422 | `VALIDATION_ERROR` | "校验失败" | 表单字段红字（zod 同步显示） |
| 429 | `RATE_LIMITED` | "请求过于频繁，请稍后再试" | 退避重试（TanStack Query 自动） |
| 5xx | `SERVER_ERROR` | "服务暂不可用" | ErrorState 重试 |
| 0 / 网络 | `NETWORK_ERROR` | "网络异常" | ErrorState 重试 |

后端在 `app/core/exceptions.py` 应统一返回 `{ "code": "...", "detail": "..." }`，前端 normalize 后映射；后端没给 code 时按 HTTP status fallback。

### 2.4 Token Refresh

MVP 简化：access token 15min 过期，401 直接跳登录（不做 refresh token 自动刷新）。理由：试点客户每天打开 1-2 次，5min cache TTL 内重新登录可接受；refresh token 流程复杂且容易出 race。Track B / 客户反馈强烈时再补。

---

## 3. 通用三态组件 API

### 3.1 何时用什么

| 场景 | 组件 |
|---|---|
| 调接口、骨架占位 | `LoadingSkeleton`（或 `shadcn/Skeleton` 单独用于行内小占位） |
| 数据返回但为空 | `EmptyState` |
| 调接口失败 / 渲染崩溃 | `ErrorState` |
| 数据正常 | 业务组件本身 |

**核心区别**：`shadcn/Skeleton` 是**原子**（一个灰色矩形），`LoadingSkeleton` 是**组合**（一个屏的完整占位结构，如三栏工作台用 `<LoadingSkeleton variant="workbench" />`）。

### 3.2 EmptyState API

```typescript
// src/components/shared/EmptyState.tsx
interface EmptyStateProps {
  icon?: React.ReactNode               // lucide-react icon
  title: string                        // 主标题（用 font-content text-h3）
  description?: string                 // 说明
  action?: { label: string; onClick: () => void }   // 主按钮
  className?: string
}
```

用法：

```tsx
<EmptyState
  icon={<FolderOpen className="size-12 text-text-subtle" />}
  title="还没有项目"
  description="新建一个项目，接入数据源后即可看到事件流"
  action={{ label: '+ 新建项目', onClick: () => navigate('/projects/new') }}
/>
```

### 3.3 ErrorState API

```typescript
interface ErrorStateProps {
  title?: string                       // 默认"加载失败"
  error?: ApiError | Error | string    // 失败详情（自动 narrow）
  onRetry?: () => void                 // 给则显示重试按钮
  variant?: 'inline' | 'fullscreen'    // 内联（行级）vs 整页
}
```

`error` 必须用 `unknown` narrow（参考 `~/.claude/rules/typescript/coding-style.md`）：

```typescript
function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object' && 'message' in error) {
    return String(error.message)
  }
  return '未知错误'
}
```

### 3.4 LoadingSkeleton 的 variants

| variant | 用途 | 主调用方 |
|---|---|---|
| `workbench` | 三栏（左侧栏 / 中间事件流 / 右侧 todos） | T03 |
| `list` | 卡片网格（3x2） | T05 / T15 |
| `document` | 大纲 + 章节占位 | T06 / T09 |
| `form` | 表单字段堆叠 | T01 / T02 / T13 / T14 |
| `drawer` | 抽屉内骨架（顶部 header + 列表） | T04 / T07 |
| `card` | 单卡内文字行 | 通用 |

每个 variant 大概 10-30 行 JSX，组合 `shadcn/Skeleton`。

---

## 4. Zustand stores 设计

### 4.1 authStore

```typescript
// src/stores/authStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  display_name: string
  is_instance_admin: boolean
}

interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  setAuth: (user: User, token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      setAuth: (user, accessToken) => set({ user, accessToken, isAuthenticated: true }),
      logout: () => set({ user: null, accessToken: null, isAuthenticated: false }),
    }),
    { name: 'tokenknows_auth' },
  ),
)
```

**持久化**：全 persist 到 localStorage（key 名 `tokenknows_auth`，与任务包 T01 §8 一致）。

### 4.2 projectStore

```typescript
interface ProjectState {
  currentProjectId: string | null
  setCurrent: (id: string | null) => void
}
```

**持久化**：persist 到 localStorage（key `tokenknows_current_project`）。切项目时 main.tsx 顶层用 `useEffect` 触发 `queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'projects' && q.queryKey[1] === oldId })`。

### 4.3 uiStore

```typescript
interface UiState {
  sidebarOpen: boolean
  notificationOpen: boolean
  toggleSidebar: () => void
}
```

**持久化**：不 persist（每次会话独立）。

### 4.4 documentUiStore

T06 / T07 / T08 共享：

```typescript
interface DocumentUiState {
  // T07 证据抽屉
  evidenceOpen: boolean
  activeEvidenceId: string | null

  // T04 事件抽屉
  eventDrawerOpen: boolean
  activeEventId: string | null

  // T08 重生成对话框
  regenerateOpen: boolean
  regenerateChapterId: string | null

  // actions
  openEvidence: (id: string) => void
  closeEvidence: () => void
  openEventDrawer: (id: string) => void
  closeEventDrawer: () => void
  openRegenerate: (chapterId: string) => void
  closeRegenerate: () => void
}
```

**持久化**：不 persist。但 `activeEvidenceId` / `activeEventId` 与 URL query string 同步（深链支持，见任务包 T04 / T07）。

### 4.5 反模式（严格禁止）

- ❌ 把服务端数据（项目列表、事件流、文档详情）塞进 Zustand
- ❌ 把表单临时 state 塞进 Zustand（用 `react-hook-form`）
- ❌ 在 store 里调 API（actions 应该是纯 state mutation，API 调用在组件 / hook 里）

---

## 5. TanStack Query 全局配置 + queryKey 表

### 5.1 全局配置

```typescript
// src/main.tsx（已有，扩充 defaultOptions）
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,           // 30s 内不重新 fetch
      gcTime: 5 * 60_000,          // 5min 后从 cache 移除
      retry: (failureCount, error) => {
        const apiErr = error as ApiError
        if (apiErr.status >= 400 && apiErr.status < 500) return false  // 4xx 不重试
        return failureCount < 2
      },
      refetchOnWindowFocus: false, // 默认关；个别 query 单独开
    },
    mutations: {
      retry: false,                // mutation 不自动重试
    },
  },
})
```

### 5.2 queryKey 命名规范

**层级**：`[resource, scope?, id?, sub-resource?, params?]`

- 资源用单数复数与 REST 一致（`projects` `events` `assets`）
- 第一层是 invalidate 的最大粒度
- params 放在最后一层，按字母序排列后 stringify（避免顺序差异导致 cache miss）

### 5.3 15 任务 queryKey 完整表

| 任务 | Key | TTL | 用法 |
|---|---|---|---|
| T01 | `['me']` | 默认 | `useQuery(['me'], () => api.get('/me'))` |
| T02 | `['projects']`（invalidate after create） | 默认 | — |
| T03 | `['projects', id]` | 默认 | 项目详情 |
| T03 | `['projects', id, 'events', filters]` | 10s | 事件流（短 staleTime，配 polling） |
| T03 | `['projects', id, 'stats']` | 60s | 数字卡 |
| T03 | `['projects', id, 'todos']` | 默认 | 本周待办 |
| T04 | `['events', eventId]` | 5min | 事件详情（drawer 内）|
| T05 | `['projects', id, 'assets', filters]` | 默认 | 文档列表 |
| T06 | `['assets', assetId]` | 默认 | 文档详情 |
| T06 | `['assets', assetId, 'chapters']` | 默认 | 章节列表 |
| T07 | `['assets', assetId, 'chapters', chapterId, 'evidence']` | 默认 | 证据 |
| T08 | `['projects', id, 'llm', 'models']` | 5min | 可用模型 allowlist |
| T09 | `['assets', assetId]`（与 T06 共享） | — | 只读视图 |
| T10 | `['assets', assetId, 'redaction', { jobId }]` | 2s | 异步 scan polling |
| T11 | — | — | 全是 mutation |
| T12 | `['publish-records', publishId]` | 默认 | 回执详情 |
| T12 | `['assets', assetId, 'versions', v1, 'diff', v2]` | 默认 | 版本 diff |
| T13 | `['projects', id, 'members']` | 默认 | — |
| T13 | `['projects', id, 'datasources']` | 默认 | — |
| T13 | `['projects', id, 'datasources', dsId, 'health']` | 30s | 健康检查 |
| T14 | `['projects', id, 'llm-config']` | 默认 | — |
| T14 | `['egress-log', filters]` | 默认 | 出域日志 |
| T15 | `['admin', 'stats']` | 60s | — |
| T15 | `['admin', 'users', filters]` | 默认 | — |
| T15 | `['audit-log', filters]` | 默认 | — |

### 5.4 SSE / polling 协同模式

**T03 工作台**：

```typescript
// MVP 阶段（W1-W3）：纯 polling
useQuery({
  queryKey: ['projects', id, 'events', filters],
  queryFn: () => api.get(`/projects/${id}/events`, { params: filters }),
  refetchInterval: 30_000,
  refetchIntervalInBackground: false,   // tab 失焦时停
})

// W4D17 联调日：替换为 SSE
// 仍然保留上面这个 useQuery 作为初始加载 + fallback；
// 加一个 useEffect 订阅 EventSource，新事件 push 到 cache：
useEffect(() => {
  const es = new EventSource(`/api/v1/ws/projects/${id}/events`, { withCredentials: true })
  es.addEventListener('event', (e) => {
    const newEvent = JSON.parse(e.data)
    queryClient.setQueryData(['projects', id, 'events', filters], (old: Event[] | undefined) =>
      old ? [newEvent, ...old] : [newEvent])
  })
  return () => es.close()
}, [id, filters, queryClient])
```

**T10 异步 scan polling**：

```typescript
// 提交 scan 任务返回 job_id；每 2s 查状态直到 done
useQuery({
  queryKey: ['assets', assetId, 'redaction', { jobId }],
  queryFn: () => api.get(`/assets/${assetId}/redaction/scan`, { params: { job_id: jobId } }),
  enabled: !!jobId,
  refetchInterval: (q) => (q.state.data?.status === 'done' ? false : 2000),
})
```

---

## 6. MSW handlers 框架

### 6.1 文件组织（**按 resource 分文件**）

```
src/mocks/
├── browser.ts           # workers().start()
├── handlers.ts          # 聚合 exports
├── fixtures/
│   ├── users.ts         # 1 个测试用户
│   ├── projects.ts      # 3 个项目
│   ├── events.ts        # 50 条事件（4 种 source）
│   ├── assets.ts        # 2 份文档（draft + reviewing）
│   └── audit.ts         # 20 条日志
└── handlers/
    ├── auth.ts          # /auth/*, /me
    ├── projects.ts      # /projects/* CRUD
    ├── datasources.ts
    ├── events.ts
    ├── assets.ts        # 含 generation / chapters / evidence
    ├── redaction.ts     # 异步 scan
    ├── publish.ts       # 含 export
    └── admin.ts
```

### 6.2 handlers.ts 聚合

```typescript
// src/mocks/handlers.ts
import { authHandlers } from './handlers/auth'
import { projectHandlers } from './handlers/projects'
// ...
export const handlers = [
  ...authHandlers,
  ...projectHandlers,
  ...datasourceHandlers,
  ...eventHandlers,
  ...assetHandlers,
  ...redactionHandlers,
  ...publishHandlers,
  ...adminHandlers,
]
```

### 6.3 错误注入开关

每个 handler 文件顶部有一个 in-memory toggle，方便手动测错态：

```typescript
// src/mocks/handlers/projects.ts
const ERROR_MODE = new URLSearchParams(window.location.search).get('mock_error')

export const projectHandlers = [
  http.get('/api/v1/projects', () => {
    if (ERROR_MODE === 'projects') return HttpResponse.json({ code: 'SERVER_ERROR', detail: 'mocked 500' }, { status: 500 })
    return HttpResponse.json({ data: fixtureProjects })
  }),
]
```

测错态时 URL 加 `?mock_error=projects` 即可。

### 6.4 不要在 mock 里写业务逻辑

MSW handlers 只 echo fixtures + 简单 in-memory state（如 create / delete 项目时 push / splice），**不要做真的逻辑**（如 trust_score 计算）。复杂的下游响应（如 T06 文档结构）直接用 fixture JSON，由 hand-crafted demo 数据驱动。

---

## 7. 路由结构

### 7.1 顶层（已有 `src/routes/index.tsx`，待重构为 lazy + layout）

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppLayout } from '@/components/layouts/AppLayout'
import { AuthLayout } from '@/components/layouts/AuthLayout'
import { AdminLayout } from '@/components/layouts/AdminLayout'
import { RequireAuth, RequireRole } from '@/components/guards'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'

const LoginPage = lazy(() => import('@/features/auth/LoginPage'))
const WorkbenchPage = lazy(() => import('@/features/workbench/WorkbenchPage'))
// ...其余 15 屏

const lazyRoute = (Component: React.LazyExoticComponent<any>) => (
  <Suspense fallback={<LoadingSkeleton variant="form" />}>
    <Component />
  </Suspense>
)

export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [
      { path: '/login',           element: lazyRoute(LoginPage) },
      { path: '/register',        element: lazyRoute(RegisterPage) },
      { path: '/verify-email',    element: lazyRoute(VerifyEmailPage) },
      { path: '/forgot-password', element: lazyRoute(ForgotPasswordPage) },
      { path: '/reset-password',  element: lazyRoute(ResetPasswordPage) },
    ],
  },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { path: '/',                                                element: lazyRoute(WorkbenchPage) },
      { path: '/projects/new',                                    element: lazyRoute(NewProjectPage) },
      { path: '/projects/:id',                                    element: lazyRoute(WorkbenchPage) },
      { path: '/projects/:id/documents',                          element: lazyRoute(DocumentListPage) },
      { path: '/projects/:id/documents/:docId',                   element: lazyRoute(DocumentPage) },
      { path: '/projects/:id/documents/:docId/review',            element: <RequireRole role="reviewer">{lazyRoute(ReviewPage)}</RequireRole> },
      { path: '/projects/:id/documents/:docId/redaction',         element: lazyRoute(RedactionPage) },
      { path: '/projects/:id/documents/:docId/published/:publishId', element: lazyRoute(PublishReceiptPage) },
      { path: '/projects/:id/settings/*',                         element: lazyRoute(ProjectSettingsPage) },
    ],
  },
  {
    element: <RequireAuth><RequireRole role="instance_admin"><AdminLayout /></RequireRole></RequireAuth>,
    children: [
      { path: '/admin',         element: lazyRoute(AdminStatsPage) },
      { path: '/admin/users',   element: lazyRoute(AdminUsersPage) },
      { path: '/admin/quotas',  element: lazyRoute(AdminQuotasPage) },
      { path: '/admin/audit',   element: lazyRoute(AdminAuditPage) },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
```

### 7.2 RequireAuth / RequireRole

```typescript
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const location = useLocation()
  if (!isAuthenticated) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`} replace />
  }
  return <>{children}</>
}

export function RequireRole({ role, children }: { role: 'reviewer' | 'owner' | 'instance_admin'; children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  // MVP: role 检查在前端只是 UX，后端依旧强校验。
  if (!user) return <Navigate to="/login" replace />
  if (role === 'instance_admin' && !user.is_instance_admin) return <Navigate to="/" replace />
  // reviewer / owner 需要项目级 membership 校验，由具体页面在 useQuery 里读 project.role 二次确认
  return <>{children}</>
}
```

### 7.3 三套 Layout

| Layout | 用途 | 关键样式 |
|---|---|---|
| `AuthLayout` | T01 系列 | 左侧品牌区（`bg-bg-warm`）+ 右侧表单卡 |
| `AppLayout` | 主业务屏 T02-T13 | 顶栏（实例信息 + 项目选择 + 用户）+ 左侧导航 + 主区 + 抽屉槽位（右侧 / 底部） |
| `AdminLayout` | T15 | 深色顶栏（`bg-inverse-bg text-inverse-text`） + sub-nav |

抽屉槽位用 React Portal 渲染到 AppLayout 内的 `<div id="drawer-slot">`，由 T04/T07 抽屉组件挂载。

---

## 8. 设计 token 落地裁决（**修 src/index.css 的 bug**）

### 8.1 现状（已通过 Read 确认）

`src/styles/tokens.css` 是 SSOT：

```css
:root {
  --color-bg-card: #faf9f5;
  /* ... 完整自定义 token */
  /* shadcn 兼容 mapping */
  --background: var(--color-bg-page);
  --card: var(--color-bg-card);
  --primary: var(--color-accent-primary);
  /* ... */
}
```

但 `src/index.css` 在引入 tokens.css **之后**又重新定义了一遍 `:root`：

```css
:root {
  --background: oklch(1 0 0);          /* ← 把 tokens.css 的暖米色覆盖回纯白 */
  --primary: oklch(0.205 0 0);         /* ← 陶土橙变回黑色 */
  /* ... */
}
```

**这是 bug**。css 后定义覆盖前面，结果就是 shadcn 组件（用 `--background` / `--primary`）失去品牌色，回到 monochrome。

### 8.2 修复决策

**保留 tokens.css 为 SSOT，删掉 index.css 里重复的 `:root` 与 `.dark` 块**。修改后的 `src/index.css`：

```css
@import "tailwindcss";
@config "../tailwind.config.ts";
@import "./styles/tokens.css";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/geist";
@import "@fontsource/poppins/400.css";
@import "@fontsource/poppins/500.css";
@import "@fontsource/poppins/600.css";
@import "@fontsource/lora/400.css";
@import "@fontsource/lora/600.css";

@custom-variant dark (&:is(.dark *));

@theme inline {
  /* 保留所有 @theme inline 的 mapping —— 这是 tailwind v4 把 CSS 变量暴露成 utility 的桥梁 */
  /* ...（保留 12-77 行的内容） */
}

/* 删除 53-86 行 :root 块 */
/* 删除 88-120 行 .dark 块（dark mode 由 tokens.css §10 之后版本统一管理；MVP 不实现 dark mode） */

@layer base {
  * { @apply border-border outline-ring/50; }
  body { @apply bg-background text-foreground; }
  html { @apply font-sans; }
}
```

### 8.3 字体加载（npm 命令）

```bash
npm install @fontsource/poppins @fontsource/lora
```

这样 `font-ui (Poppins)` 与 `font-content (Lora)` class 才会真正生效，而不是回退到 Georgia / -apple-system。`tokens.css` 第 78 行 `body { font-family: 'Poppins', ... }` 也才能拿到真字体。

### 8.4 Tailwind class 使用规则（强约束）

| 场景 | 用什么 | 例 |
|---|---|---|
| 业务屏样式 | **自定义 token 直接 utility** | `bg-bg-card text-text-primary border-border-subtle` `font-content text-h1` |
| shadcn 组件内部（生成的 `components/ui/*.tsx`） | **shadcn 默认 utility**（实际指向自定义 token，因为 tokens.css 做了 mapping） | `bg-card text-foreground border-border` |
| 禁用 | 原生 Tailwind 色 | ❌ `bg-stone-50 text-gray-900` |

业务代码读完 §8.2 修复后，**shadcn 组件渲染出来的颜色 = 自定义陶土橙/暖米色板**——这是关键。

### 8.5 验证

W1D1 修完 index.css 后跑：

```bash
npm run dev
# 打开 / 路由（App.tsx 占位页）
# 应看到：bg-bg-page 暖米色背景 + 陶土橙 CTA 按钮 + serif 字体的 h1（Lora）
# 同时 shadcn Button 默认 variant 应该也是陶土橙（因为 --primary 已经 mapping）
```

---

## 9. 品牌主题系统（PRD §5.7 G1）

### 9.1 MVP 决策：**不做**

**预留 hook，不暴露 UI**。理由：试点客户都用默认陶土橙就够 demo；多品牌切换是 Phase 2 的事。

### 9.2 预留实现路径

`tokens.css` 的 `:root` 已经把所有色板抽到 CSS 变量。Phase 2 加品牌切换时：

```typescript
// src/lib/brand-theme.ts（Phase 2）
export function applyBrandTheme(theme: { primary?: string; bg?: string; logo?: string }) {
  if (theme.primary) document.documentElement.style.setProperty('--color-accent-primary', theme.primary)
  if (theme.bg) document.documentElement.style.setProperty('--color-bg-page', theme.bg)
  // logo 通过 store 注入到 AppLayout 顶栏
}
```

无需重写组件，因为所有 utility 已经走 CSS 变量。

### 9.3 导出渲染（PDF / docx）

T11 导出时品牌主题应用，由后端模板引擎读项目 `brand_theme` JSON（PRD §6.6.3）注入。前端只需把项目 brand_theme 存在 projects 表里、PATCH `/projects/:id` 时附带即可。

---

## 10. i18n 策略（PRD §6.4）

### 10.1 MVP 决策：**仅 zh-CN，不预埋 react-i18next**

**理由**：
- 试点客户全是中文团队
- 预埋 i18n 但只一种语言 = 净增加 `t('foo.bar')` 调用噪音
- 即使要加 en，把硬编码中文文案抽 keys 是机械工作，5 天能干完，不必预埋

### 10.2 例外：日期 / 数字 / 相对时间

用 `date-fns`（已装）+ `date-fns/locale/zh-CN`：

```typescript
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'

formatDistanceToNow(new Date(event.occurred_at), { addSuffix: true, locale: zhCN })
// → "3 小时前"
```

千位分隔符直接 `Intl.NumberFormat('zh-CN').format(n)`，无需 i18n。

### 10.3 Phase 2 引入条件

签到 ≥ 1 家英文用户 / 客户主动询问时再引入 react-i18next。届时按文件批量抽 keys + 添加 en.json。

---

## 11. a11y 与键盘清单

每屏交付时必过 4 条硬指标：

| 指标 | 实施 | 验证 |
|---|---|---|
| **Tab 顺序合理** | 元素 DOM 顺序 = 视觉顺序；无 `tabIndex={-1}` 除非有理由 | 实测 Tab 走一圈 |
| **焦点环可见** | 所有 interactive element 有 `focus-visible:ring-2 ring-accent-primary outline-none` | Tab 后能看到 |
| **Esc 关 drawer / modal** | shadcn Dialog / Sheet 默认支持，自定义抽屉时手动加 keydown listener | Esc 测一遍 |
| **Enter 主操作 / Cmd+Enter 提交大表单** | form `onSubmit` + button `type="submit"`；TipTap 章节内 Cmd+Enter = 触发重生成 | 键盘测一遍 |

### 11.2 ARIA 最低限度

- 所有 icon-only button 加 `aria-label`
- `Dialog` / `Sheet` 来自 shadcn，已有 `aria-labelledby` / `aria-describedby`，**不要删**
- 进度条用 `<Progress>` + `aria-valuenow / aria-valuetext`
- 表单字段 `<Label htmlFor>` 配对（react-hook-form + shadcn 已默认）

### 11.3 颜色对比

设计 token 已经按 WCAG AA 选过（DesignHandoff §2.1）。**不要**自己调浅色文字 + 浅色背景。

---

## 12. 性能预算分配（PRD §6.1 SLA 拆到每屏）

### 12.1 整体 SLA（PRD §6.1）

| 维度 | P95 | 备注 |
|---|---|---|
| 工作台首屏加载 | < 2s | T03 |
| 实时事件流端到端延迟 | < 5s | 插件→工作台 |
| 单份文档生成（~2000 字） | < 60s | T05 触发，T06 等待 |
| 大文档渲染 ≥ 10k 字 | 首字 < 3s | T06 流式渲染 |
| 搜索 / 过滤事件流 | < 500ms | T03 |

### 12.2 工作台 2s 预算拆解（示例）

| 阶段 | 预算 | 实施手段 |
|---|---|---|
| TLS + HTML 加载 | 200ms | gzip / brotli、HTTP/2 |
| JS bundle 解析 + 执行 | 400ms | Vite lazy load 分屏；初始 chunk < 200KB gzip |
| 数据请求（`projects/:id` + events + stats） | 600ms | 并行发起，TanStack Query 自动并发 |
| 渲染（三栏 + 50 条事件卡） | 500ms | `react-window` 列表虚拟化 |
| 余量 | 300ms | — |

### 12.3 各屏的"快速预算"

| 屏 | 关键性能动作 |
|---|---|
| T01 | 表单几乎无成本；登录响应 < 500ms |
| T02 | 4 步向导，每步 < 1s；token 复制 toast 即时 |
| T03 | 见 §12.2 |
| T05 | 列表分页 cursor，每页 20 条；切 filter < 300ms |
| T06 | TipTap 初始化 + markdown 渲染 < 2s；自动保存 < 200ms |
| T10 | scan 是异步 job，polling 2s 间隔；前端响应即时 |
| T11 | 发布请求 → 跳 T12 < 2s |
| T12 | diff 计算 < 1s（Vite worker 跑 `diff` lib） |

### 12.4 包体积守门

```bash
# 每周末跑一次
npm run build
# 查看 dist/assets/*.js 大小
# 初始 chunk（main.tsx + 必要 layout + auth）应 < 250KB gzip
# 每个 lazy chunk < 150KB gzip
# 如果超：检查是否误把 TipTap / recharts 打进主 chunk（应 lazy）
```

---

## 附录 A · 立即可执行的"地基日"清单（W1D1）

```bash
# 1. 修 token bug + 加字体（约 30 分钟）
#    编辑 src/index.css：删 :root 重复块、删 .dark 块、加 @fontsource imports
cd /Users/wujun/TokenKnows/code/tokenknows-web
npm install @fontsource/poppins @fontsource/lora

# 2. 写 src/lib/api.ts（约 30 分钟，按 §2.1 抄）

# 3. 写 src/components/shared/{EmptyState,ErrorState,LoadingSkeleton}.tsx（约 60 分钟）

# 4. 写 src/stores/{authStore,projectStore,uiStore,documentUiStore}.ts（约 60 分钟）

# 5. 写 src/types/api.ts（DTO，按 TDD §6.1 端点 + §5 schema 翻译，约 60 分钟）

# 6. 写 3 套 Layout：AuthLayout, AppLayout, AdminLayout（约 90 分钟）

# 7. 重构 src/routes/index.tsx：lazy + layout + guards（约 30 分钟）

# 8. 写 src/mocks/handlers/auth.ts + me（让 T01 next day 能跑，约 30 分钟）

# 9. 验证：npm run dev → / 路由可见 bg-bg-page + 陶土橙 + Lora 字体；localStorage 见 tokenknows_auth 占位
```

总计 ~6 小时，**与 README 现有 W1D1"路由 + AppLayout 骨架 + 通用 EmptyState/ErrorState/Skeleton 组件 6h"完全对齐**。SharedFoundations 把"模糊 6 小时"拆成可执行清单。

---

## 附录 B · 与全局规则的兼容性自检

| 规则 | 来源 | 本文档实施 |
|---|---|---|
| 用 `unknown` 不用 `any` | `~/.claude/rules/typescript/coding-style.md` | §2.3 `normalizeError` 用 AxiosError 泛型 + getErrorMessage narrow |
| Props 用 named interface | 同上 | §3.2 `EmptyStateProps` / §3.3 `ErrorStateProps` 均 interface |
| zod 做 runtime validation | `~/.claude/rules/typescript/patterns.md` | T01 表单 + 错误归一时 zod 校验后端响应（细节在 TaskTechDesign T01） |
| Repository Pattern | 同上 | `lib/api.ts` 作为通用 client；具体 resource 的 CRUD 在 features/hooks/ 内包装（不抽专门的 repository class） |
| Playwright E2E | `~/.claude/rules/typescript/testing.md` | TaskTechDesign Part 6 E2E 骨架用 Playwright |
| 不留 `console.log` | `~/.claude/rules/typescript/hooks.md` | dev 期允许，CI 加 ESLint rule `no-console: warn` |
| 永远从环境变量读 secret | `~/.claude/rules/typescript/security.md` | 前端不持有任何 secret；token 在 localStorage，仅 access token，refresh 由后端单独 cookie |

---

**版本历史**

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v0.1 | 2026-05-20 | 初稿 12 节 + W1D1 清单 | John + Claude |
