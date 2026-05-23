/**
 * MarketplacePage · v1.0 T70 unit tests.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import MarketplacePage from './MarketplacePage'

const mock = new MockAdapter(api)

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mock.reset()
  useProjectStore.setState({ currentProjectId: null, projects: [] })
})

afterEach(() => {
  useProjectStore.setState({ currentProjectId: null, projects: [] })
})

const _seedItem = (overrides: Record<string, unknown> = {}) => ({
  skill_id: 's-1',
  name: 'demo',
  version: 1,
  project_id: 'proj-A',
  trust_score: 0.7,
  usage_count: 10,
  acceptance_count: 8,
  published_at: '2026-06-01T00:00:00Z',
  skill_md_preview: '# demo content',
  ...overrides,
})

describe('MarketplacePage', () => {
  it('empty list → EmptyState', async () => {
    mock.onGet(/\/marketplace\/skills/).reply(200, { items: [], total: 0 })
    _render(<MarketplacePage />)
    await waitFor(() =>
      expect(screen.getByText(/暂无匹配/)).toBeInTheDocument(),
    )
  })

  it('renders cards from API', async () => {
    mock.onGet(/\/marketplace\/skills/).reply(200, {
      items: [
        _seedItem({ skill_id: 'a', name: 'pr-summary' }),
        _seedItem({ skill_id: 'b', name: 'background' }),
      ],
      total: 2,
    })
    _render(<MarketplacePage />)
    await waitFor(() =>
      expect(screen.getByTestId('marketplace-list')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('market-card-a')).toBeInTheDocument()
    expect(screen.getByTestId('market-card-b')).toBeInTheDocument()
    expect(screen.getByText('pr-summary')).toBeInTheDocument()
  })

  it('search triggers refetch with q param', async () => {
    mock.onGet(/\/marketplace\/skills/).reply((config) => {
      const url = config.url || ''
      if (url.includes('q=foo')) {
        return [200, {
          items: [_seedItem({ skill_id: 'found', name: 'foo-bar' })],
          total: 1,
        }]
      }
      return [200, { items: [], total: 0 }]
    })
    _render(<MarketplacePage />)
    // 等初始 empty
    await waitFor(() =>
      expect(screen.getByText(/暂无匹配/)).toBeInTheDocument(),
    )
    fireEvent.change(screen.getByTestId('marketplace-q'), {
      target: { value: 'foo' },
    })
    fireEvent.click(screen.getByTestId('marketplace-search-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('market-card-found')).toBeInTheDocument(),
    )
  })

  it('import button disabled when no current project', async () => {
    mock.onGet(/\/marketplace\/skills/).reply(200, {
      items: [_seedItem()],
      total: 1,
    })
    _render(<MarketplacePage />)
    await waitFor(() =>
      expect(screen.getByTestId('market-card-s-1')).toBeInTheDocument(),
    )
    const btn = screen.getByTestId('import-s-1') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.textContent).toContain('请先选项目')
  })

  it('import POST with current project', async () => {
    useProjectStore.setState({
      currentProjectId: 'proj-B',
      projects: [],
    })
    mock.onGet(/\/marketplace\/skills/).reply(200, {
      items: [_seedItem()],
      total: 1,
    })
    mock.onPost('/projects/proj-B/skills/import').reply(201, {
      id: 'new-skill',
      project_id: 'proj-B',
      name: 'demo',
      version: 1,
    })
    _render(<MarketplacePage />)
    await waitFor(() =>
      expect(screen.getByTestId('import-s-1')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('import-s-1'))
    await waitFor(() => expect(mock.history.post.length).toBe(1))
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.source_skill_id).toBe('s-1')
    // 导入后显示 "已导入"
    await waitFor(() =>
      expect(screen.getByTestId('imported-s-1')).toBeInTheDocument(),
    )
  })

  it('error state with retry', async () => {
    mock.onGet(/\/marketplace\/skills/).reply(500)
    _render(<MarketplacePage />)
    await waitFor(() =>
      expect(screen.getByText(/加载市场失败/)).toBeInTheDocument(),
    )
  })
})
