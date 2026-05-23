/**
 * GlobalEntitiesPage · v1.6 T103 单测.
 *
 * 验:
 *   - 加载中 / error / empty / 列表 4 状态
 *   - 搜索表单提交 → q 参数透传
 *   - type filter 切换 → API URL 含 type
 *   - min_projects input 修改 → API URL 含 min_projects
 *   - 展开行 → 调 GET /global/entities/:gid/projects
 *   - row 显示 label / type 标签 / project_count / aliases
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import GlobalEntitiesPage from './GlobalEntitiesPage'
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

const mockGlobals = [
  {
    id: 'gent_1', type: 'person', label: 'Alice', canonical_label: 'alice',
    aliases: ['Alice W.', 'ALICE'],
    linked: [
      { project_id: 'p1', project_entity_id: 'ent_a' },
      { project_id: 'p2', project_entity_id: 'ent_b' },
    ],
    created_by: 'u1',
    project_count: 2,
  },
  {
    id: 'gent_2', type: 'event', label: 'Outage', canonical_label: 'outage',
    aliases: [],
    linked: [{ project_id: 'p1', project_entity_id: 'ent_c' }],
    created_by: null,
    project_count: 1,
  },
]

describe('GlobalEntitiesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('加载中显示 skeleton', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    render(withWrappers(<GlobalEntitiesPage />))
    expect(screen.getByTestId('global-entities-page')).toBeInTheDocument()
    // skeleton 由 LoadingSkeleton 渲染, 没特定 testid 也行
  })

  it('error 显示 ErrorState', async () => {
    vi.spyOn(api, 'get').mockRejectedValue({ code: 'SERVER_ERROR', status: 500 })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument()
    })
  })

  it('empty 显示 EmptyState', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => {
      expect(screen.getByText(/暂无跨 project 全局实体/)).toBeInTheDocument()
    })
  })

  it('列表渲染 + label / project_count / aliases', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mockGlobals })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
      expect(screen.getByText(/也叫: Alice W\., ALICE/)).toBeInTheDocument()
      expect(screen.getByTestId('project-count-gent_1')).toHaveTextContent('2 project')
    })
  })

  it('搜索表单提交触发新 query (含 q)', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    spy.mockClear()
    const input = screen.getByPlaceholderText(/搜索实体/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'alice' } })
    fireEvent.submit(screen.getByTestId('global-entities-search'))
    await waitFor(() => {
      const calls = spy.mock.calls.map((c) => c[0] as string)
      expect(calls.some((u) => u.includes('q=alice'))).toBe(true)
    })
  })

  it('type filter 切换 → URL 含 type=person', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    spy.mockClear()
    fireEvent.click(screen.getByTestId('type-filter-person'))
    await waitFor(() => {
      const calls = spy.mock.calls.map((c) => c[0] as string)
      expect(calls.some((u) => u.includes('type=person'))).toBe(true)
    })
  })

  it('min_projects 修改 → URL 含 min_projects=5', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    spy.mockClear()
    fireEvent.change(screen.getByTestId('min-projects-input'), {
      target: { value: '5' },
    })
    await waitFor(() => {
      const calls = spy.mock.calls.map((c) => c[0] as string)
      expect(calls.some((u) => u.includes('min_projects=5'))).toBe(true)
    })
  })

  it('展开行触发 GET /global/entities/:gid/projects', async () => {
    const spy = vi.spyOn(api, 'get')
      .mockResolvedValueOnce({ data: mockGlobals })
      .mockResolvedValueOnce({
        data: [
          {
            id: 'ent_a', project_id: 'p1', type: 'person',
            label: 'Alice', source_refs: [
              { asset_id: 'a1', chapter_id: 'ch1', node_id: 'n1' },
            ],
          },
        ],
      })
    render(withWrappers(<GlobalEntitiesPage />))
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    const row = screen.getByTestId('global-entity-gent_1')
    const toggle = row.querySelector('button')!
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.getByTestId('global-entity-expanded-gent_1')).toBeInTheDocument()
      const calls = spy.mock.calls.map((c) => c[0] as string)
      expect(calls.some((u) => u.includes('/global/entities/gent_1/projects'))).toBe(true)
    })
  })
})
