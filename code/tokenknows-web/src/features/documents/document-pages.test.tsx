/**
 * DocumentListPage + DocumentPage · T05 / T06 page-level smoke tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import DocumentListPage from './DocumentListPage'
import DocumentPage from './DocumentPage'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'draft', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: '亮点', content: 'content', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
  ...overrides,
})


function withList(ui: ReactNode, path = '/projects/p1/documents') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

function withDoc(ui: ReactNode, path = '/projects/p1/documents/a1') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('DocumentListPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders header + generate button', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('项目文档')).toBeInTheDocument())
    expect(screen.getByText('生成新文档')).toBeInTheDocument()
  })

  it('empty list shows EmptyState', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText(/还没有文档/)).toBeInTheDocument())
  })

  it('filtered no result shows different empty text', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withList(<DocumentListPage />, '/projects/p1/documents?type=adr'))
    await waitFor(() => expect(screen.getByText(/该条件下没有文档/)).toBeInTheDocument())
  })

  it('renders asset cards from data', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset({ id: 'a-1', title: '周报 W21' }), mkAsset({ id: 'a-2', title: 'ADR-007', type: 'adr' })],
        meta: { total: 2, cursor: null, has_more: false },
      },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('周报 W21')).toBeInTheDocument())
    expect(screen.getByText('ADR-007')).toBeInTheDocument()
  })

  it('hasNextPage: 加载更多 button', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset()],
        meta: { total: 99, cursor: 'cursor-x', has_more: true },
      },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('加载更多')).toBeInTheDocument())
  })

  it('clicking 生成新文档 opens dialog', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('生成新文档')).toBeInTheDocument())
    fireEvent.click(screen.getByText('生成新文档'))
    await waitFor(() => expect(screen.getByText('文档类型')).toBeInTheDocument())
  })

  it('error state on fetch failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('文档列表加载失败')).toBeInTheDocument())
  })
})


describe('DocumentPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loading state initially', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    const { container } = render(withDoc(<DocumentPage />))
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('error state on fetch failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withDoc(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('文档加载失败')).toBeInTheDocument())
  })

  it('renders 3 columns + chapters when data loads', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter({ title: '亮点章节' })] })
      return Promise.resolve({ data: mkAsset({ title: '周报 X' }) })
    })
    render(withDoc(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('周报 X')).toBeInTheDocument())
    expect(screen.getByText('亮点章节')).toBeInTheDocument()
  })

  it('renders empty state when chapters empty', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset({ status: 'generating' }) })
    })
    render(withDoc(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('章节尚未生成')).toBeInTheDocument())
  })
})
