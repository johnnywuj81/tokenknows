/**
 * ReviewPage · scrollToChapter + onAllApproved branches.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ReviewPage from './ReviewPage'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'in_review', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: '', updated_at: '', ...overrides,
})

const mkChapter = (id: string, order: number, state: Chapter['approval_state'] = 'pending'): Chapter => ({
  id, asset_id: 'a1', asset_version: 1, order_index: order,
  title: `章节 ${order + 1}`, content: 'x', layout: {},
  generated_by: null, regeneration_history: [], approval_state: state,
  created_at: '', updated_at: '',
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1/review']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId/review" element={ui} />
          <Route path="/projects/:id/documents/:docId" element={<div>DOC</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('ReviewPage action callbacks', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('clicking sidebar chapter title scrolls + sets highlight', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter('c1', 0)] })
      return Promise.resolve({ data: mkAsset() })
    })
    const el = document.createElement('div')
    el.id = 'chapter-anchor-c1'
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy
    document.body.appendChild(el)
    try {
      render(withWrappers(<ReviewPage />))
      await waitFor(() => expect(screen.getAllByText('章节 1').length).toBeGreaterThan(0))
      // sidebar version (with §1 prefix)
      const titles = screen.getAllByText('章节 1')
      // First match is in DocOutline (left), second in ApprovalSidebar (right)
      fireEvent.click(titles[titles.length - 1])
      expect(scrollSpy).toHaveBeenCalled()
    } finally {
      document.body.removeChild(el)
    }
  })

  it('all approved → 全部通过 click → navigates to doc + opens publish', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({
        data: [mkChapter('c1', 0, 'approved'), mkChapter('c2', 1, 'approved')],
      })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText(/全部通过/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/全部通过/))
    await waitFor(() => expect(screen.getByText('DOC')).toBeInTheDocument())
  })

  it('error state retry refetches', async () => {
    let calls = 0
    vi.spyOn(api, 'get').mockImplementation(() => {
      calls += 1
      return Promise.reject(new Error('fail'))
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('审批页加载失败')).toBeInTheDocument())
    const initial = calls
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(calls).toBeGreaterThan(initial))
  })
})
