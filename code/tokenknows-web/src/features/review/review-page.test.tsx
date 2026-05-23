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
import type { Asset, Chapter, KnowledgeGraphLayout } from '@/types/api'


// T125 · 在 jsdom 下 mock GraphCanvas 避免 React Flow 内部 crash;
// 仅断言 ReviewPage 进 KG 分支 + 把 layout 透传过来.
vi.mock('../documents/knowledge-graph/GraphCanvas', () => ({
  GraphCanvas: ({ layout }: { layout: KnowledgeGraphLayout }) => (
    <div data-testid="kg-graph-canvas">
      canvas: {layout.nodes.length}n {layout.edges.length}e
    </div>
  ),
}))


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

  // T125 · KG 资产: 应当渲染图谱 + 节点审计表, 不再走 markdown chapter 列表
  it('renders KG canvas + node table for knowledge_graph asset', async () => {
    const kgLayout: KnowledgeGraphLayout = {
      schema_version: 'kg.v1',
      nodes: [
        {
          id: 'n_alice',
          type: 'person',
          label: 'Alice',
          properties: {},
          source_event_ids: ['e1'],
          trust_score: 0.9,
          span_anchor: { char_offset: 0 },
        },
        {
          id: 'n_event_x',
          type: 'event',
          label: 'Launch X',
          properties: {},
          source_event_ids: ['e1'],
          trust_score: 0.8,
          span_anchor: { char_offset: 30 },
        },
      ],
      edges: [
        {
          id: 'rel_1',
          source: 'n_alice',
          target: 'n_event_x',
          type: 'authored_by',
          weight: 1,
          source_event_ids: ['e1'],
        },
      ],
      layout_hints: { algorithm: 'dagre', rankdir: 'LR' },
    }
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters/') && url.endsWith('/evidence')) {
        return Promise.resolve({ data: [] })
      }
      if (url.includes('/chapters')) {
        return Promise.resolve({
          data: [mkChapter({ id: 'kg-c1', layout: kgLayout })],
        })
      }
      return Promise.resolve({
        data: mkAsset({ type: 'knowledge_graph', title: 'KG · X' }),
      })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() =>
      expect(screen.getByTestId('kg-graph-canvas')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('reviewer-node-table')).toBeInTheDocument()
    // 不应渲染 markdown chapter 列表 (空标题 placeholder)
    expect(screen.queryByText('无章节可审批')).not.toBeInTheDocument()
  })

  // T125 · KG 资产但 layout 是空 dict (legacy / parse_error) → 回退到 markdown 渲染
  it('falls back to markdown chapter render when KG layout is empty', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) {
        return Promise.resolve({
          data: [mkChapter({ id: 'kg-c0', layout: {}, title: '占位章节' })],
        })
      }
      return Promise.resolve({
        data: mkAsset({ type: 'knowledge_graph', title: 'KG empty' }),
      })
    })
    render(withWrappers(<ReviewPage />))
    await waitFor(() => expect(screen.getByText('审批 · KG empty')).toBeInTheDocument())
    expect(screen.queryByTestId('kg-graph-canvas')).not.toBeInTheDocument()
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
