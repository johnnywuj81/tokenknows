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
    // v0.9 T67: MembersPanel 走真 API; mock 空列表
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/members')) {
        return Promise.resolve({
          data: {
            project_id: 'p1',
            items: [],
            owner_count: 0,
            reviewer_count: 0,
            contributor_count: 0,
          },
        })
      }
      return Promise.resolve({ data: mkProject() })
    })
    render(withWrappers(<ProjectSettingsPage />))
    await waitFor(() => expect(screen.getByText('项目设置')).toBeInTheDocument())
    const memberButtons = screen.getAllByText('成员')
    fireEvent.click(memberButtons[0])
    // v0.9 MembersPanel 空 project 显示 bootstrap CTA
    await waitFor(() =>
      expect(screen.getByText(/项目尚未配置成员/)).toBeInTheDocument(),
    )
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

  it('member roles all rendered (owner + reviewer)', async () => {
    // v0.9 T67: 用真 ProjectMembersResponse mock
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/members')) {
        return Promise.resolve({
          data: {
            project_id: 'p1',
            items: [
              {
                id: 'm-1', project_id: 'p1',
                user_id: 'ou-alice', role: 'owner',
                added_by: 'ou-alice', added_at: '2026-01-01',
                note: null,
              },
              {
                id: 'm-2', project_id: 'p1',
                user_id: 'ou-bob', role: 'reviewer',
                added_by: 'ou-alice', added_at: '2026-01-02',
                note: null,
              },
            ],
            owner_count: 1, reviewer_count: 1, contributor_count: 0,
          },
        })
      }
      return Promise.resolve({ data: mkProject() })
    })
    render(withWrappers(<ProjectSettingsPage />, '/projects/p1/settings?tab=members'))
    await waitFor(() =>
      expect(screen.getByTestId('members-table')).toBeInTheDocument(),
    )
    // alice row + bob row 渲染
    expect(screen.getByTestId('member-row-ou-alice')).toBeInTheDocument()
    expect(screen.getByTestId('member-row-ou-bob')).toBeInTheDocument()
    // role chips / 计数显示 (Owner/Reviewer 各 ≥ 1)
    expect(screen.getAllByText('Owner').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Reviewer').length).toBeGreaterThan(0)
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
