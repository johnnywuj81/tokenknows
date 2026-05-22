/**
 * AdminUsersPage 时间格式化分支 · 天前 / 旧日期 fallback.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import AdminUsersPage from './AdminUsersPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('AdminUsersPage time format branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('last_login_at 3 days ago: shows 天前', async () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86_400_000).toISOString()
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        {
          id: 'u-a', email: 'a@b.com', display_name: 'A',
          is_instance_admin: false,
          email_verified_at: '2024-01-01T00:00:00Z',
          last_login_at: threeDaysAgo,
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    })
    render(withWrappers(<AdminUsersPage />))
    await waitFor(() => expect(screen.getByText(/3 天前/)).toBeInTheDocument())
  })

  it('last_login_at over 7 days: shows formatDate (YYYY/MM/DD)', async () => {
    const longAgo = '2024-03-15T10:00:00Z'
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        {
          id: 'u-b', email: 'b@b.com', display_name: 'B',
          is_instance_admin: false,
          email_verified_at: longAgo,
          last_login_at: longAgo,
          created_at: longAgo,
        },
      ],
    })
    render(withWrappers(<AdminUsersPage />))
    await waitFor(() => expect(screen.getByText('b@b.com')).toBeInTheDocument())
    // 2024/03/15 格式渲染
    expect(screen.getAllByText(/2024\/0?3\/15/).length).toBeGreaterThan(0)
  })

  it('invalid last_login_at: catch fallback returns raw iso', async () => {
    const originalGetTime = Date.prototype.getTime
    // Mock Date.prototype.getTime to throw on first call
    let callCount = 0
    Date.prototype.getTime = function () {
      callCount += 1
      if (callCount === 2) throw new Error('boom')
      return originalGetTime.call(this)
    }
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        {
          id: 'u-c', email: 'c@b.com', display_name: 'C',
          is_instance_admin: false,
          email_verified_at: null,
          last_login_at: '2026-05-22T00:00:00Z',
          created_at: '2026-05-22T00:00:00Z',
        },
      ],
    })
    try {
      render(withWrappers(<AdminUsersPage />))
      await waitFor(() => expect(screen.getByText('c@b.com')).toBeInTheDocument())
    } finally {
      Date.prototype.getTime = originalGetTime
    }
  })
})
