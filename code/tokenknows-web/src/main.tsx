import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { router } from './routes'
import { isApiError } from './lib/api'
import './index.css'

/**
 * TanStack Query 全局配置 · 设计依据 SharedFoundations.md §5.1
 *
 * - staleTime 30s: 30s 内不重新 fetch
 * - gcTime 5min: 5min 后从 cache 移除
 * - retry: 4xx 不重试,网络/5xx 至多重试 2 次
 * - refetchOnWindowFocus: false (默认关,个别 query 单独开)
 * - mutations 不自动重试
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) => {
        if (isApiError(error) && error.status >= 400 && error.status < 500) {
          return false
        }
        return failureCount < 2
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})

/**
 * MSW disable 开关 (T141 二阶段):
 * - 自愈失败后 watchdog 会持久化设这个 flag → 下次启动彻底不 register SW
 * - URL 加 ?msw=0 也能临时禁
 * - URL 加 ?msw=1 可强制重新启用 (clear flag)
 * - 走 backend 真路径 (/projects, /projects/:id, /stats, /todos, etc. 都已落 backend)
 */
const MSW_DISABLED_KEY = 'tk-msw-disabled'

function isMSWDisabled(): boolean {
  if (typeof window === 'undefined') return false
  const url = new URLSearchParams(window.location.search)
  if (url.get('msw') === '0') {
    localStorage.setItem(MSW_DISABLED_KEY, '1')
    return true
  }
  if (url.get('msw') === '1') {
    localStorage.removeItem(MSW_DISABLED_KEY)
    return false
  }
  return localStorage.getItem(MSW_DISABLED_KEY) === '1'
}

async function enableMocking(): Promise<void> {
  if (!import.meta.env.DEV) return
  if (isMSWDisabled()) {
    // eslint-disable-next-line no-console
    console.info('[MSW] disabled (走 backend 真路径). 加 ?msw=1 重新启用.')
    // 万一之前残留 SW, 顺手清掉避免 SW lifecycle 卡 fetch
    if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map((r) => r.unregister()))
    }
    return
  }
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'bypass' })
}

/**
 * MSW + Vite HMR 老 bug · 二阶段 (T141):
 *
 * dev server 反复重启 / SW 状态错乱后, service worker 注册着但 handler 死了.
 * 浏览器 fetch 被 SW 拦但 SW 不响应 → 请求 hang in pending → UI 永远 skeleton.
 * (MSW 已知问题: https://github.com/mswjs/msw/issues/96 + #98)
 *
 * 解法分层 (上层失败往下降):
 *   L1. 30s 探测 /api/v1/__msw_health__ 看 MSW 是否 alive.
 *   L2. 连续 2 次失败 → unregister SW + reload (一次性自愈).
 *   L3. 自愈后仍失败 → 设 tk-msw-disabled flag + reload, **从此 session 不用 MSW**,
 *       走 backend 真路径 (/projects /stats /todos 等已落 backend, mock-only 端点
 *       如 POST /projects 会 404, 用户能看到错误而不是 skeleton 卡死).
 *
 * 跟之前比, 不再"放弃" → 永远会让 user 拿到一个可用 UI.
 */
function startMSWWatchdog(): void {
  if (!import.meta.env.DEV) return
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return
  if (isMSWDisabled()) return  // 已经在 no-MSW 模式, 不用监控
  // T144 (HIGH-3): SELF_HEAL_KEY 必须用 localStorage 不能用 sessionStorage —
  // L2 自愈会 reload, sessionStorage 在 reload 时会被清空, 标记丢失 →
  // 下次失败仍走 L2 路径无限 reload loop, L3 永远不触发. 用 localStorage
  // 让标志跨 reload 存活, 真正进入"自愈失败 → L3 disable MSW" 路径.
  const SELF_HEAL_KEY = 'tk-msw-self-healed'
  const INTERVAL_MS = 30_000
  const FAIL_THRESHOLD = 2
  let consecFailures = 0

  setInterval(async () => {
    let alive = false
    try {
      const r = await fetch('/api/v1/__msw_health__', { cache: 'no-store' })
      if (r.status === 200) {
        const body = (await r.json().catch(() => ({}))) as { msw?: boolean }
        alive = body?.msw === true
      }
    } catch {
      /* network err == not alive */
    }

    if (alive) {
      consecFailures = 0
      localStorage.removeItem(SELF_HEAL_KEY)
      return
    }

    consecFailures += 1
    if (consecFailures < FAIL_THRESHOLD) return

    if (!localStorage.getItem(SELF_HEAL_KEY)) {
      // L2: 第一次自愈尝试 (标记跨 reload 存活, 下次失败才能进 L3)
      localStorage.setItem(SELF_HEAL_KEY, '1')
      // eslint-disable-next-line no-console
      console.warn('[MSW watchdog] SW not intercepting; unregistering + reloading (1/2)')
      try {
        const regs = await navigator.serviceWorker.getRegistrations()
        await Promise.all(regs.map((reg) => reg.unregister()))
      } finally {
        window.location.reload()
      }
      return
    }

    // L3: 自愈过仍死 → fallback 到 no-MSW 模式
    // eslint-disable-next-line no-console
    console.warn(
      '[MSW watchdog] SW unrecoverable; switching to no-MSW mode permanently for this session. ' +
        'Backend 真路径会接管. 加 ?msw=1 可强制重启 MSW.',
    )
    localStorage.setItem(MSW_DISABLED_KEY, '1')
    try {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map((reg) => reg.unregister()))
    } finally {
      window.location.reload()
    }
  }, INTERVAL_MS)
}

// T144 (HIGH-2): enableMocking() reject 时之前没 .catch, app 不 mount →
// 用户看空白页, 无错误反馈. 这是用户反复抱怨"刷新就 skeleton 卡死"的
// 症状之一. 现在 mock 失败时也强制 mount, 让 backend 真路径接管.
function renderApp(): void {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  )
}

enableMocking()
  .then(() => {
    startMSWWatchdog()
    renderApp()
  })
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(
      '[bootstrap] enableMocking failed; mounting app without MSW (走 backend 真路径)',
      err,
    )
    renderApp()
  })
