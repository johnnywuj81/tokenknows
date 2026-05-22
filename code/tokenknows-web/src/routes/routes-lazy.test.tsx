/**
 * routes/index.tsx Lazy() function · 通过 createMemoryRouter + RouterProvider 渲染 trigger Lazy 包装函数.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/lib/api'

// 引入路由表
import { router as originalRouter } from './index'

void originalRouter // 让 import 副作用执行


describe('routes index Lazy()', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
  })

  it('renders /login through Lazy Suspense wrapper', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })

    // 复用 originalRouter.routes 但用 memory router
    const memRouter = createMemoryRouter(
      originalRouter.routes,
      { initialEntries: ['/login'] },
    )
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const { container } = render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={memRouter} />
      </QueryClientProvider>,
    )

    // 等待 lazy 加载 LoginPage 完成
    await waitFor(() => {
      const html = container.textContent || ''
      expect(html).toContain('TokenKnows')
    }, { timeout: 3000 })
  })
})
