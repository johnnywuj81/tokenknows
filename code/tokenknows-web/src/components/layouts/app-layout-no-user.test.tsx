/**
 * AppLayout 分支 · 无 user 时不渲染用户信息区.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { AppLayout } from './AppLayout'
import { useAuthStore } from '@/stores/authStore'
import { useProjectStore } from '@/stores/projectStore'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route element={ui}>
            <Route path="/" element={<div data-testid="content">OK</div>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('AppLayout no-user branch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useProjectStore.setState({ currentProjectId: null })
  })

  it('user=null: no user name or Admin link rendered', () => {
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<AppLayout />))
    expect(screen.queryByText(/Admin/)).toBeNull()
    // outlet still rendered
    expect(screen.getByTestId('content')).toBeInTheDocument()
  })
})
