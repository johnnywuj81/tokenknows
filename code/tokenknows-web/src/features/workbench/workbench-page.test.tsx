/**
 * WorkbenchPage · T03 三栏工作台.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import WorkbenchPage from './WorkbenchPage'
import { api } from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'


function withWrappers(ui: ReactNode, path = '/projects/p1') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id" element={ui} />
          <Route path="/" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('WorkbenchPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useProjectStore.setState({ currentProjectId: null })
  })

  it('no projects: shows EmptyWorkbench', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<WorkbenchPage />, '/'))
    await waitFor(() => expect(screen.getByText(/建立你的研发知识空间/)).toBeInTheDocument())
  })

  it('projects load error: shows error state', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('boom'))
    render(withWrappers(<WorkbenchPage />, '/'))
    await waitFor(() => expect(screen.getByText('加载项目失败')).toBeInTheDocument())
  })

  it('renders 3 columns when project loads', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.endsWith('/projects/p1')) {
        return Promise.resolve({
          data: {
            id: 'p1', name: 'My Project', description: null,
            owner_id: 'u1', llm_egress_enabled: false, task_egress_config: {},
            custom_redaction_terms: [], brand_theme: {},
            created_at: '', updated_at: '',
          },
        })
      }
      if (url.includes('/stats')) return Promise.resolve({ data: { events_today: 5, drafts: 2, in_review: 1, published: 3 } })
      if (url.includes('/todos')) return Promise.resolve({ data: [] })
      if (url.includes('/datasources/health')) return Promise.resolve({ data: { items: [], window_days: 30, total_active: 0, total_events_window: 0, total_events_all: 0 } })
      if (url.includes('/events')) return Promise.resolve({ data: { data: [], meta: { total: 0, cursor: null, has_more: false } } })
      return Promise.resolve({ data: [] })
    })
    render(withWrappers(<WorkbenchPage />))
    await waitFor(() => expect(screen.getByText('My Project')).toBeInTheDocument())
  })

  it('URL paramId syncs to store', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<WorkbenchPage />, '/projects/abc'))
    await waitFor(() => {
      expect(useProjectStore.getState().currentProjectId).toBe('abc')
    })
  })

  it('project error: shows project error state', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.endsWith('/projects/p1')) return Promise.reject(new Error('not found'))
      return Promise.resolve({ data: [] })
    })
    render(withWrappers(<WorkbenchPage />))
    await waitFor(() => expect(screen.getByText('项目加载失败')).toBeInTheDocument())
  })

  it('no paramId but projects exist: auto-selects first', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [{ id: 'auto-1', name: 'Auto Project', description: null,
        owner_id: 'u1', llm_egress_enabled: false, task_egress_config: {},
        custom_redaction_terms: [], brand_theme: {}, created_at: '', updated_at: '' }],
    })
    render(withWrappers(<WorkbenchPage />, '/'))
    await waitFor(() => {
      expect(useProjectStore.getState().currentProjectId).toBe('auto-1')
    })
  })
})
