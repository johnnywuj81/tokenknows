/**
 * Workbench 余下组件 · ProjectSwitcher + EventStream + EventDrawer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ProjectSwitcher } from './ProjectSwitcher'
import { EventStream } from './EventStream'
import { EventDrawer } from './EventDrawer'
import { api } from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Event, Project } from '@/types/api'


const mkProject = (id: string, name: string): Project => ({
  id, name, description: null, owner_id: 'u1',
  llm_egress_enabled: false, task_egress_config: {},
  custom_redaction_terms: [], brand_theme: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
})

const mkEvent = (overrides: Partial<Event> = {}): Event => ({
  id: 'e1',
  project_id: 'p1',
  source_type: 'github',
  source_ref: 'org/repo#1',
  external_id: 'gh-1',
  version: 1,
  event_type: 'pr_event',
  occurred_at: new Date().toISOString(),
  ingested_at: new Date().toISOString(),
  author: { name: 'Alice', email: 'a@example.com' },
  title: 'feat: 加新功能',
  content: 'some content here for testing purposes',
  payload: { html_url: 'https://github.com/org/repo/pull/1' },
  redaction_state: 'screened',
  trust_score: 0.92,
  tags: ['merged'],
  content_hash: 'abc',
  ...overrides,
})


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


// ─── ProjectSwitcher ──────────────────────────────────────


describe('ProjectSwitcher', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useProjectStore.setState({ currentProjectId: null })
  })

  it('renders "选择项目" when no current id', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<ProjectSwitcher />))
    expect(screen.getByText('选择项目')).toBeInTheDocument()
  })

  it('renders "加载中..." when current id but no data', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    useProjectStore.setState({ currentProjectId: 'p9' })
    render(withWrappers(<ProjectSwitcher />))
    expect(screen.getByText('加载中...')).toBeInTheDocument()
  })

  it('renders current project name when data loaded', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [mkProject('p1', 'Project Alpha')],
    })
    useProjectStore.setState({ currentProjectId: 'p1' })
    render(withWrappers(<ProjectSwitcher />))
    await waitFor(() => expect(screen.getByText('Project Alpha')).toBeInTheDocument())
  })
})


// ─── EventStream ──────────────────────────────────────────


describe('EventStream', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows empty state with no events + no source filter', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() =>
      expect(screen.getByText('尚无事件流入')).toBeInTheDocument(),
    )
  })

  it('renders events grouped by day', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [
          mkEvent({ id: 'e1', title: 'event-today-1' }),
          mkEvent({ id: 'e2', title: 'event-today-2' }),
        ],
        meta: { total: 2, cursor: null, has_more: false },
      },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => {
      expect(screen.getByText('今天')).toBeInTheDocument()
      expect(screen.getByText('event-today-1')).toBeInTheDocument()
      expect(screen.getByText('event-today-2')).toBeInTheDocument()
    })
  })

  it('renders 昨天 group', async () => {
    const y = new Date()
    y.setDate(y.getDate() - 1)
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkEvent({ id: 'e1', occurred_at: y.toISOString(), title: 'y1' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => expect(screen.getByText('昨天')).toBeInTheDocument())
  })

  it('renders error state on fetch fail', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('boom'))
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() =>
      expect(screen.getByText('事件流加载失败')).toBeInTheDocument(),
    )
  })

  it('clicking event card opens drawer via store', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkEvent({ id: 'e-click', title: 'click-me' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    useDocumentUiStore.setState({ eventDrawerOpen: false, activeEventId: null })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => expect(screen.getByText('click-me')).toBeInTheDocument())
    await act(async () => {
      fireEvent.click(screen.getByText('click-me'))
    })
    expect(useDocumentUiStore.getState().eventDrawerOpen).toBe(true)
    expect(useDocumentUiStore.getState().activeEventId).toBe('e-click')
  })

  it('refresh button triggers refetch', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => expect(screen.getByText('尚无事件流入')).toBeInTheDocument())
    spy.mockClear()
    fireEvent.click(screen.getByLabelText('立即刷新'))
    await waitFor(() => expect(spy).toHaveBeenCalled())
  })

  it('hasNextPage: 加载更早 button rendered', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkEvent({ id: 'e1' })],
        meta: { total: 99, cursor: 'cursor-x', has_more: true },
      },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() =>
      expect(screen.getByText('加载更早')).toBeInTheDocument(),
    )
  })
})


// ─── EventDrawer ──────────────────────────────────────────


describe('EventDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({ eventDrawerOpen: false, activeEventId: null })
  })

  it('hidden when not open', () => {
    render(withWrappers(<EventDrawer />))
    expect(screen.queryByText('事件详情')).toBeNull()
  })

  it('shows loading then event detail', async () => {
    let resolveFn: ((v: { data: Event }) => void) | null = null
    vi.spyOn(api, 'get').mockReturnValueOnce(
      new Promise((res) => { resolveFn = res }),
    )
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    expect(screen.getByText(/加载事件中/)).toBeInTheDocument()

    await act(async () => {
      resolveFn!({ data: mkEvent({ id: 'e1', title: '事件标题', payload: { html_url: 'https://x.test' } }) })
    })

    await waitFor(() => {
      expect(screen.getByText('事件标题')).toBeInTheDocument()
      expect(screen.getByText('Alice')).toBeInTheDocument()
      expect(screen.getByText('在源头打开')).toBeInTheDocument()
    })
  })

  it('renders error state on fetch fail', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件加载失败')).toBeInTheDocument())
  })

  it('trust badge: high (>=0.8) green', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ trust_score: 0.92 }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText(/TRUST 92/)).toBeInTheDocument())
  })

  it('trust badge: medium (0.5-0.8) info', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ trust_score: 0.6 }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText(/TRUST 60/)).toBeInTheDocument())
  })

  it('trust badge: low (<0.5) warning', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ trust_score: 0.3 }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText(/TRUST 30/)).toBeInTheDocument())
  })

  it('is_private event shows sensitive badge', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ is_private: true }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText(/敏感来源/)).toBeInTheDocument())
  })

  it('redaction badges: all 4 states', async () => {
    const states: Event['redaction_state'][] = ['raw', 'screened', 'confirmed', 'exported']
    const labels = ['原始', '已扫描', '已确认', '已导出']
    for (let i = 0; i < states.length; i++) {
      vi.spyOn(api, 'get').mockResolvedValue({
        data: mkEvent({ redaction_state: states[i] }),
      })
      useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: `e-${i}` })
      const { unmount } = render(withWrappers(<EventDrawer />))
      await waitFor(() => expect(screen.getByText(labels[i])).toBeInTheDocument())
      unmount()
    }
  })

  it('payload toggle expands JSON view', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ payload: { key: 'value', n: 42 } }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText(/原始 Payload/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/原始 Payload/))
    await waitFor(() => expect(screen.getByText(/"value"/)).toBeInTheDocument())
  })

  it('event without title falls back to event_type label', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ title: null, event_type: 'pr_event' }),
    })
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => {
      // 'PR 事件' appears in both header and "事件类型" cell
      const all = screen.getAllByText('PR 事件')
      expect(all.length).toBeGreaterThan(0)
    })
  })
})
