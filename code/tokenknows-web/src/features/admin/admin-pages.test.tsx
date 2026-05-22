/**
 * Admin pages · AdminStatsPage + AdminUsersPage + AdminQuotasPage + AdminAuditPage.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import AdminStatsPage from './AdminStatsPage'
import AdminUsersPage from './AdminUsersPage'
import AdminQuotasPage from './AdminQuotasPage'
import AdminAuditPage from './AdminAuditPage'
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


describe('AdminStatsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders title + 4 stat cards (from fallback when api fails)', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('not implemented'))
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('实例管理')).toBeInTheDocument())
    expect(screen.getByText('实例用户')).toBeInTheDocument()
    expect(screen.getByText('活跃项目')).toBeInTheDocument()
    expect(screen.getByText('本月产出文档')).toBeInTheDocument()
    expect(screen.getByText('本月 LLM tokens')).toBeInTheDocument()
  })

  it('renders fallback numbers when api fails', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument())
    expect(screen.getByText('27')).toBeInTheDocument()
  })

  it('storage progress bar rendered', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('存储')).toBeInTheDocument())
    expect(screen.getByText(/8\.6%|8\.\d%/)).toBeInTheDocument()
  })

  it('3 sub-nav cards rendered', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('用户列表')).toBeInTheDocument())
    expect(screen.getByText('审计日志')).toBeInTheDocument()
    expect(screen.getByText('LLM 全局配置')).toBeInTheDocument()
  })

  it('successful api call uses returned data', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        users_total: 99,
        projects_total: 7,
        assets_this_month: 100,
        llm_tokens_this_month: 1_500_000,
        storage_used_bytes: 5_000_000,
        storage_limit_bytes: 21_474_836_480,
      },
    })
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('99')).toBeInTheDocument())
    expect(screen.getByText('1.5M')).toBeInTheDocument()
  })

  it('formatLargeNumber: K format (1000-999999)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        users_total: 1, projects_total: 1, assets_this_month: 1,
        llm_tokens_this_month: 5500,
        storage_used_bytes: 100, storage_limit_bytes: 1000,
      },
    })
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('5.5K')).toBeInTheDocument())
  })
})


describe('AdminUsersPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders user list (fallback) when api fails', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<AdminUsersPage />))
    await waitFor(() => expect(screen.getByText('demo@tokenknows.local')).toBeInTheDocument())
    expect(screen.getByText('alice@tokenknows.local')).toBeInTheDocument()
  })

  it('admin badge rendered for instance admin', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<AdminUsersPage />))
    await waitFor(() => expect(screen.getByText(/Admin/i)).toBeInTheDocument())
  })

  it('successful api call uses returned users', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        { id: 'u-x', email: 'x@y.com', display_name: 'X', is_instance_admin: false,
          email_verified_at: null, last_login_at: null, created_at: '' },
      ],
    })
    render(withWrappers(<AdminUsersPage />))
    await waitFor(() => expect(screen.getByText('x@y.com')).toBeInTheDocument())
  })
})


describe('AdminQuotasPage', () => {
  it('renders placeholder', () => {
    render(withWrappers(<AdminQuotasPage />))
    expect(screen.getByText(/配额管理/)).toBeInTheDocument()
  })
})


describe('AdminAuditPage', () => {
  it('renders placeholder', () => {
    render(withWrappers(<AdminAuditPage />))
    expect(screen.getByText(/审计日志/)).toBeInTheDocument()
  })
})
