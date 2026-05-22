/**
 * ReviewPage · T09 reviewer page.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ReviewPage from './ReviewPage'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报 W21',
  status: 'in_review', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: '', updated_at: '',
  ...overrides,
})

const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: '亮点', content: '内容', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
  ...overrides,
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
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('ReviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading skeleton initially', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    const { container } = render(withWrappers(<ReviewPage />))
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('error state on asset load failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('审批页加载失败')).toBeInTheDocument())
  })

  it('renders header + chapters', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({
        data: [mkChapter({ id: 'c1', title: '亮点' }), mkChapter({ id: 'c2', order_index: 1, title: '风险' })],
      })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('审批 · 周报 W21')).toBeInTheDocument())
    expect(screen.getAllByText('待审批').length).toBeGreaterThan(0)
    expect(screen.getByText('0 / 2 已通过')).toBeInTheDocument()
  })

  it('renders approval badge for approved status', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset({ approval_state: 'approved' }) })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('已通过')).toBeInTheDocument())
  })

  it('renders approval badge for rejected', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset({ approval_state: 'rejected' }) })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('已退回')).toBeInTheDocument())
  })

  it('empty chapters shows 无章节可审批', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('无章节可审批')).toBeInTheDocument())
  })

  it('back button rendered', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText(/返回文档/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/返回文档/))
  })

  it('chapter approval progress count', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({
        data: [
          mkChapter({ id: 'c1', approval_state: 'approved' }),
          mkChapter({ id: 'c2', approval_state: 'pending' }),
        ],
      })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('1 / 2 已通过')).toBeInTheDocument())
  })
})
