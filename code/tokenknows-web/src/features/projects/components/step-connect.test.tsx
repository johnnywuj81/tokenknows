/**
 * StepConnect · 整合多种 connector + useAddDatasource.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { StepConnect } from './StepConnect'
import { api } from '@/lib/api'
import type { Datasource, Project } from '@/types/api'


const mockProject: Project = {
  id: 'p1',
  name: 'demo',
  description: '',
  owner_id: 'u1',
  llm_egress_enabled: false,
  task_egress_config: {},
  custom_redaction_terms: [],
  brand_theme: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


describe('StepConnect', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders PluginConnector for claude_code', () => {
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['claude_code']}
      addedDatasources={[]}
      onDatasourceAdded={() => {}}
    />))
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('生成连接 token')).toBeInTheDocument()
  })

  it('renders GitHubConnector for github', () => {
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['github']}
      addedDatasources={[]}
      onDatasourceAdded={() => {}}
    />))
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByLabelText(/Personal Access Token/)).toBeInTheDocument()
  })

  it('renders LocalFileConnector for local_file', () => {
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['local_file']}
      addedDatasources={[]}
      onDatasourceAdded={() => {}}
    />))
    expect(screen.getByText('本地文件')).toBeInTheDocument()
    expect(screen.getByText(/稍后上传/)).toBeInTheDocument()
  })

  it('handleCreate flow: click 生成 → onDatasourceAdded called', async () => {
    const mockDs: Datasource = {
      id: 'd1',
      project_id: 'p1',
      type: 'claude_code',
      name: 'plugin',
      config: {},
      connection_token: 'tk.abc.def',
      health: 'healthy',
      last_synced_at: null,
      created_at: new Date().toISOString(),
    }
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mockDs })
    const onAdded = vi.fn()
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['claude_code']}
      addedDatasources={[]}
      onDatasourceAdded={onAdded}
    />))
    fireEvent.click(screen.getByText('生成连接 token'))
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/projects/p1/datasources/claude_code',
        {},
      )
      expect(onAdded).toHaveBeenCalledWith(mockDs)
    })
  })

  it('github submit flow: POST with body', async () => {
    const mockDs: Datasource = {
      id: 'd2',
      project_id: 'p1',
      type: 'github',
      name: 'repos',
      config: { repos: ['a/b'] },
      health: 'healthy',
      last_synced_at: null,
      created_at: new Date().toISOString(),
    }
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mockDs })
    const onAdded = vi.fn()
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['github']}
      addedDatasources={[]}
      onDatasourceAdded={onAdded}
    />))
    fireEvent.change(screen.getByLabelText(/Personal Access Token/), {
      target: { value: 'ghp_xxx' },
    })
    fireEvent.change(screen.getByLabelText(/仓库/), { target: { value: 'a/b' } })
    fireEvent.click(screen.getByText('校验并接入'))
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/projects/p1/datasources/github',
        { pat: 'ghp_xxx', repos: ['a/b'] },
      )
      expect(onAdded).toHaveBeenCalledWith(mockDs)
    })
  })

  it('error path: clears activeType on error (no callback)', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('fail'))
    const onAdded = vi.fn()
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['cursor']}
      addedDatasources={[]}
      onDatasourceAdded={onAdded}
    />))
    fireEvent.click(screen.getByText('生成连接 token'))
    await waitFor(() => {
      expect(onAdded).not.toHaveBeenCalled()
    })
  })

  it('addedDatasources passed-through: shows connected', () => {
    const ds: Datasource = {
      id: 'd1',
      project_id: 'p1',
      type: 'claude_code',
      name: 'cc',
      config: {},
      connection_token: 'a.b.c',
      health: 'healthy',
      last_synced_at: null,
      created_at: new Date().toISOString(),
    }
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['claude_code']}
      addedDatasources={[ds]}
      onDatasourceAdded={() => {}}
    />))
    expect(screen.getByText('已连接')).toBeInTheDocument()
  })

  it('unknown type returns null (no crash)', () => {
    // 一个类型不在 5 个分支里 - 通过强转测试 default branch
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['weird' as 'github']}
      addedDatasources={[]}
      onDatasourceAdded={() => {}}
    />))
    // 不渲染卡片就好
    expect(screen.queryByText('GitHub')).toBeNull()
  })
})
