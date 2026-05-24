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

async function enableMocking() {
  if (!import.meta.env.DEV) return
  const { worker } = await import('./mocks/browser')
  return worker.start({ onUnhandledRequest: 'bypass' })
}

/**
 * MSW + Vite HMR 老 bug: dev server 反复重启 / SW 状态错乱后, service worker
 * 仍在 navigator 里登记着, 但不再拦截 fetch → 所有 /api/v1/* 透传到真后端 →
 * 真后端没实现的端点返 404 → "项目加载失败 Not Found".
 *
 * 解法: 每 30s 探测 /api/v1/__msw_health__ (MSW 注册了, 真后端没):
 *   - 期望 200 + {msw:true}, 拿不到 → SW 死了 → unregister + reload.
 *   - 每 session 只自愈一次 (防 reload 死循环).
 */
function startMSWWatchdog() {
  if (!import.meta.env.DEV) return
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return
  const RELOAD_KEY = 'tk-msw-self-healed'
  const INTERVAL_MS = 30_000
  const FAIL_THRESHOLD = 2  // 防抖: 连续 2 次失败才动手
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
      sessionStorage.removeItem(RELOAD_KEY)
      return
    }

    consecFailures += 1
    if (consecFailures < FAIL_THRESHOLD) return
    if (sessionStorage.getItem(RELOAD_KEY)) {
      // eslint-disable-next-line no-console
      console.warn('[MSW watchdog] still dead after one self-heal; giving up to avoid reload loop')
      return
    }

    sessionStorage.setItem(RELOAD_KEY, '1')
    // eslint-disable-next-line no-console
    console.warn('[MSW watchdog] service worker not intercepting; unregistering + reloading')
    try {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map((reg) => reg.unregister()))
    } finally {
      window.location.reload()
    }
  }, INTERVAL_MS)
}

enableMocking().then(() => {
  startMSWWatchdog()
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  )
})
