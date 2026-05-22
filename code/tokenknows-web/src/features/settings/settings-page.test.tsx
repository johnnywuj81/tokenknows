/**
 * ProjectSettingsPage · T13 settings tabs + InfoTab form.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ProjectSettingsPage from './ProjectSettingsPage'
import { api } from '@/lib/api'
import type { Project } from '@/types/api'


const mkProject = (overrides: Partial<Project> = {}): Project => ({
  id: 'p1',
  name: 'demo project',
  description: '描述',
  owner_id: 'u1',
  llm_egress_enabled: false,
  task_egress_config: {},
  custom_redaction_terms: [],
  brand_theme: {},
  created_at: '',
  updated_at: '',
  ...overrides,
})


function withWrappers(ui: ReactNode, initialPath = '/projects/p1/settings') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/settings" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('ProjectSettingsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loading state initially', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    const { container } = render(withWrappers(<ProjectSettingsPage />))
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('error state on load failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('项目加载失败')).toBeInTheDocument())
  })

  it('renders 4 tabs + project name in info tab', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('项目设置')).toBeInTheDocument())
    // 4 tabs all in sidebar; 基本信息 also appears as section header → 2 instances
    expect(screen.getAllByText('基本信息').length).toBeGreaterThan(0)
    expect(screen.getByText('成员')).toBeInTheDocument()
    expect(screen.getByText('数据源')).toBeInTheDocument()
    expect(screen.getByText('LLM 与出域')).toBeInTheDocument()
  })

  it('info tab: name input prefilled + 保存 button', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject({ name: 'my proj' }) })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByLabelText('项目名称')).toBeInTheDocument())
    expect((screen.getByLabelText('项目名称') as HTMLInputElement).value).toBe('my proj')
  })

  it('info tab: save fires PATCH', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    const patchSpy = vi.spyOn(api, 'patch').mockResolvedValue({ data: {} })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('保存')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('/projects/p1', {
        name: 'demo project',
        description: '描述',
      })
    })
    await waitFor(() => expect(screen.getByText('已保存')).toBeInTheDocument())
  })

  it('info tab: save error shows message', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    vi.spyOn(api, 'patch').mockRejectedValue(new Error('保存失败 500'))
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('保存')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => expect(screen.getByText(/保存失败/)).toBeInTheDocument())
  })

  it('clicking 成员 tab switches view', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('项目设置')).toBeInTheDocument())
    const memberButtons = screen.getAllByText('成员')
    fireEvent.click(memberButtons[0])
    await waitFor(() => expect(screen.getByText('示例用户')).toBeInTheDocument())
  })

  it('数据源 tab shows datasource list', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    render(withWrappers(<ProjectSettingsPage />, '/projects/p1/settings?tab=datasources'))
    await waitFor(() => expect(screen.getByText('TokenKnows/api')).toBeInTheDocument())
    expect(screen.getByText('install-john-mac')).toBeInTheDocument()
    // 2 healthy → 2 instances of 正常 → use getAllByText
    expect(screen.getAllByText('正常').length).toBeGreaterThan(0)
    expect(screen.getByText('降级')).toBeInTheDocument()
  })

  it('llm tab switches to LlmEgressPanel', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/llm/egress')) return Promise.resolve({ data: { instance_enabled: true, project_enabled: false, providers: [] } })
      return Promise.resolve({ data: mkProject() })
    })
    render(withWrappers(<ProjectSettingsPage />, '/projects/p1/settings?tab=llm'))
    // 多个 'LLM 与出域' label - sidebar + panel header
    await waitFor(() => expect(screen.getAllByText('LLM 与出域').length).toBeGreaterThan(0))
  })

  it('back to workbench link rendered', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText(/返回工作台/)).toBeInTheDocument())
    expect(screen.getByText(/返回工作台/).closest('a')).toHaveAttribute('href', '/projects/p1')
  })

  it('member roles all rendered (owner + editor)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject() })
    render(withWrappers(<ProjectSettingsPage />, '/projects/p1/settings?tab=members'))
    await waitFor(() => expect(screen.getByText('owner')).toBeInTheDocument())
    expect(screen.getByText('editor')).toBeInTheDocument()
  })

  it('description from null falls back to empty', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject({ description: null }) })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByLabelText('简介')).toBeInTheDocument())
    expect((screen.getByLabelText('简介') as HTMLTextAreaElement).value).toBe('')
  })

  it('save button disabled when name empty', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkProject({ name: '' }) })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('保存')).toBeInTheDocument())
    expect(screen.getByText('保存').closest('button')).toBeDisabled()
  })
})
