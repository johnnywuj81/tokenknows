/**
 * NewProjectPage · T02 4-step wizard page.
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


describe('NewProjectPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders step 1 with title + 4-step stepper', () => {
    render(withWrappers(<NewProjectPage />))
    expect(screen.getByText('T02 · 新建项目')).toBeInTheDocument()
    expect(screen.getByText('建立你的研发知识空间')).toBeInTheDocument()
    expect(screen.getByLabelText(/项目名/)).toBeInTheDocument()
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('上一步 disabled at step 1', () => {
    render(withWrappers(<NewProjectPage />))
    expect(screen.getByText('上一步').closest('button')).toBeDisabled()
  })

  it('下一步 disabled when name too short', () => {
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'a' } })
    expect(screen.getByText('下一步').closest('button')).toBeDisabled()
  })

  it('step 1 → step 2: project create success', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        id: 'p1', name: 'my project', description: 'd', owner_id: 'u1',
        llm_egress_enabled: false, task_egress_config: {},
        custom_redaction_terms: [], brand_theme: {},
        created_at: '', updated_at: '',
      },
    })
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'my project' } })
    fireEvent.change(screen.getByLabelText(/简介/), { target: { value: 'd' } })
    fireEvent.click(screen.getByText('下一步'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('2 / 4')).toBeInTheDocument())
  })

  it('409 conflict triggers NAME_CONFLICT action', async () => {
    const conflictErr = Object.assign(new Error('项目名已存在'), {
      code: 'CONFLICT', status: 409,
    })
    vi.spyOn(api, 'post').mockRejectedValue(conflictErr)
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'dup' } })
    fireEvent.click(screen.getByText('下一步'))
    await waitFor(() => expect(screen.getByText('项目名已存在')).toBeInTheDocument())
    // step still 1
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('non-409 error stays at step 1', async () => {
    const err = Object.assign(new Error('服务端 500'), {
      code: 'SERVER_ERROR', status: 500,
    })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'good-name' } })
    fireEvent.click(screen.getByText('下一步'))
    // Step doesn't advance on non-409 either (project not created)
    await waitFor(() => expect(screen.getByText('1 / 4')).toBeInTheDocument())
  })

  it('exit button at step 1 with no data navigates back', () => {
    render(withWrappers(<NewProjectPage />))
    fireEvent.click(screen.getByLabelText('退出向导'))
    // no dialog open
    expect(screen.queryByText('放弃创建?')).toBeNull()
  })

  it('exit dialog when has data', () => {
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'partial' } })
    fireEvent.click(screen.getByLabelText('退出向导'))
    expect(screen.getByText('放弃创建?')).toBeInTheDocument()
  })

  it('exit dialog cancel keeps wizard open', () => {
    render(withWrappers(<NewProjectPage />))
    fireEvent.change(screen.getByLabelText(/项目名/), { target: { value: 'partial' } })
    fireEvent.click(screen.getByLabelText('退出向导'))
    fireEvent.click(screen.getByText('继续向导'))
    expect(screen.queryByText('放弃创建?')).toBeNull()
  })
})
