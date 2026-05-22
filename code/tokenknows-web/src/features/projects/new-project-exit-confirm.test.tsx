/**
 * NewProjectPage · 退出确认 dialog "放弃并返回" / "前往工作台" 确认路径.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import NewProjectPage from './NewProjectPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/new']}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('NewProjectPage exit dialog confirm', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('exit + 放弃并返回: navigates to /', () => {
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: '半途' } })
    fireEvent.click(screen.getByLabelText('退出向导'))
    expect(screen.getByText('放弃创建?')).toBeInTheDocument()
    expect(screen.getByText('放弃并返回')).toBeInTheDocument()
    fireEvent.click(screen.getByText('放弃并返回'))
    // navigate('/') - dialog closes
    expect(screen.queryByText('放弃创建?')).toBeNull()
  })

  it('exit after project created: shows 前往工作台 button', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        id: 'p1', name: 'demo', description: '', owner_id: 'u1',
        llm_egress_enabled: false, task_egress_config: {},
        custom_redaction_terms: [], brand_theme: {},
        created_at: '', updated_at: '',
      },
    })
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'demo' } })
    fireEvent.click(screen.getByText('下一步'))
    await waitFor(() => expect(screen.getByText('2 / 4')).toBeInTheDocument())
    // 现在 createdProject 已设置, 点击退出
    fireEvent.click(screen.getByLabelText('退出向导'))
    await waitFor(() => expect(screen.getByText('放弃创建?')).toBeInTheDocument())
    expect(screen.getByText(/项目"demo"已创建/)).toBeInTheDocument()
    expect(screen.getByText('前往工作台')).toBeInTheDocument()
    fireEvent.click(screen.getByText('前往工作台'))
    expect(screen.queryByText('放弃创建?')).toBeNull()
  })
})
