/**
 * AdminStatsPage 小数字分支 · llm_tokens < 1000 → raw n.toString()
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import AdminStatsPage from './AdminStatsPage'
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


describe('AdminStatsPage small numbers branch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('llm_tokens < 1000: returned as raw integer (formatLargeNumber fallback)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        users_total: 3,
        projects_total: 2,
        assets_this_month: 5,
        llm_tokens_this_month: 800, // < 1000 → raw "800"
        storage_used_bytes: 500, // < 1024 → "500 B"
        storage_limit_bytes: 2048, // 2 KB
      },
    })
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText('800')).toBeInTheDocument())
    expect(screen.getByText(/500 B/)).toBeInTheDocument()
  })

  it('storage in MB range', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        users_total: 1, projects_total: 1, assets_this_month: 1,
        llm_tokens_this_month: 100,
        storage_used_bytes: 50 * 1_048_576, // 50 MB
        storage_limit_bytes: 1_000 * 1_048_576,
      },
    })
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText(/MB/)).toBeInTheDocument())
  })

  it('storage in KB range', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        users_total: 1, projects_total: 1, assets_this_month: 1,
        llm_tokens_this_month: 100,
        storage_used_bytes: 5 * 1024, // 5 KB
        storage_limit_bytes: 100 * 1024,
      },
    })
    render(withWrappers(<AdminStatsPage />))
    await waitFor(() => expect(screen.getByText(/KB/)).toBeInTheDocument())
  })
})
