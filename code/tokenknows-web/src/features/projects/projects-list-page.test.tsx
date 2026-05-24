/**
 * ProjectsListPage · 项目列表页测试
 *
 * 覆盖:
 *   - loading / error / empty 三态
 *   - 项目卡片渲染 (描述/无描述 · health · role · stats)
 *   - 当前项目高亮 "当前" badge
 *   - 点击卡片 → setCurrent + navigate(/projects/:id)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ProjectsListPage from './ProjectsListPage'
import { api } from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import type { Project } from '@/types/api'

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'Project One',
    description: '示例描述',
    owner_id: 'u1',
    llm_egress_enabled: false,
    task_egress_config: {},
    custom_redaction_terms: [],
    brand_theme: {},
    created_at: new Date(Date.now() - 86400 * 1000 * 3).toISOString(),
    updated_at: new Date().toISOString(),
    role: 'owner',
    health: 'healthy',
    stats: {
      events_this_week: 42,
      assets_pending_review: 1,
      datasources_total: 5,
      datasources_healthy: 4,
    },
    ...overrides,
  }
}

function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects" element={ui} />
          <Route path="/projects/:id" element={<div data-testid="workbench" />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('ProjectsListPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useProjectStore.setState({ currentProjectId: null })
  })

  it('loading: 显示骨架, 无项目卡', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {})) // never resolves
    render(withWrappers(<ProjectsListPage />))
    expect(screen.queryAllByRole('button', { name: /打开项目/ })).toHaveLength(0)
  })

  it('error: 显示错误态 + 重试按钮', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('boom'))
    render(withWrappers(<ProjectsListPage />))
    await waitFor(() =>
      expect(screen.getByText('项目列表加载失败')).toBeInTheDocument(),
    )
  })

  it('empty: 显示空态 + 新建项目 CTA', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<ProjectsListPage />))
    await waitFor(() =>
      expect(screen.getByText('还没有项目')).toBeInTheDocument(),
    )
    // 顶栏 + 空态各一个 "新建项目" 链接, 至少要有一个
    expect(screen.getAllByRole('link', { name: /新建项目/ }).length).toBeGreaterThan(0)
  })

  it('list: 渲染所有项目卡 + 描述/role/stats', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        makeProject({ id: 'p1', name: 'Alpha', description: '阿尔法项目' }),
        makeProject({
          id: 'p2',
          name: 'Beta',
          description: null,
          role: 'reviewer',
          health: 'degraded',
        }),
      ],
    })
    render(withWrappers(<ProjectsListPage />))

    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument())

    expect(screen.getByText('Beta')).toBeInTheDocument()
    // 描述 / 无描述 占位
    expect(screen.getByText('阿尔法项目')).toBeInTheDocument()
    expect(screen.getByText('无描述')).toBeInTheDocument()
    // role tags
    expect(screen.getByText('owner')).toBeInTheDocument()
    expect(screen.getByText('reviewer')).toBeInTheDocument()
    // mini stats (本周事件 42 渲染两次, datasources 4/5 渲染两次)
    expect(screen.getAllByText('42').length).toBe(2)
    expect(screen.getAllByText('4/5').length).toBe(2)
    // 头部计数
    expect(screen.getByText(/共 2 个项目/)).toBeInTheDocument()
  })

  it('current project: 显示 "当前" badge, 其它不显示', async () => {
    useProjectStore.setState({ currentProjectId: 'p2' })
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        makeProject({ id: 'p1', name: 'Alpha' }),
        makeProject({ id: 'p2', name: 'Beta' }),
      ],
    })
    render(withWrappers(<ProjectsListPage />))
    await waitFor(() => expect(screen.getByText('Beta')).toBeInTheDocument())

    const alphaCard = screen.getByRole('button', { name: /打开项目 Alpha/ })
    const betaCard = screen.getByRole('button', { name: /打开项目 Beta \(当前\)/ })
    expect(alphaCard.querySelector('[title="当前活动项目"]')).toBeNull()
    expect(betaCard.querySelector('[title="当前活动项目"]')).not.toBeNull()
  })

  it('点击卡片: setCurrent + navigate(/projects/:id)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [makeProject({ id: 'p9', name: 'Target' })],
    })
    render(withWrappers(<ProjectsListPage />))
    await waitFor(() => expect(screen.getByText('Target')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /打开项目 Target/ }))

    await waitFor(() => {
      expect(useProjectStore.getState().currentProjectId).toBe('p9')
      expect(screen.getByTestId('workbench')).toBeInTheDocument()
    })
  })
})
