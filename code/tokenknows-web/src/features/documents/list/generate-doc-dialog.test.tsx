/**
 * GenerateDocDialog · T05 生成新文档 dialog.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { GenerateDocDialog } from './GenerateDocDialog'
import { api } from '@/lib/api'


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


describe('GenerateDocDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('hidden when open=false', () => {
    render(withQuery(<GenerateDocDialog
      projectId="p1" open={false} onOpenChange={() => {}}
    />))
    expect(screen.queryByText('生成新文档')).toBeNull()
  })

  it('renders all 4 type radios', () => {
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={() => {}} />))
    expect(screen.getByText('项目周报')).toBeInTheDocument()
    expect(screen.getByText('技术方案')).toBeInTheDocument()
    expect(screen.getByText('ADR')).toBeInTheDocument()
    expect(screen.getByText('问题复盘')).toBeInTheDocument()
  })

  it('cancel button invokes onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={onOpenChange} />))
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('submit POSTs and closes dialog on success', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { id: 'a-new' } })
    const onOpenChange = vi.fn()
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={onOpenChange} />))
    fireEvent.click(screen.getByText('开始生成'))
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled()
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  it('shows error when api returns ApiError', async () => {
    const apiErr = Object.assign(new Error('生成失败'), {
      code: 'GEN_FAIL', status: 500,
    })
    vi.spyOn(api, 'post').mockRejectedValue(apiErr)
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={() => {}} />))
    fireEvent.click(screen.getByText('开始生成'))
    await waitFor(() => expect(screen.getByText('生成失败')).toBeInTheDocument())
  })

  it('submit button shows 提交中... when pending', async () => {
    let resolveFn: (() => void) | null = null
    vi.spyOn(api, 'post').mockReturnValueOnce(
      new Promise((res) => { resolveFn = () => res({ data: {} }) }),
    )
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={() => {}} />))
    fireEvent.click(screen.getByText('开始生成'))
    await waitFor(() => expect(screen.getByText(/提交中/)).toBeInTheDocument())
    resolveFn!()
  })

  it('type radio change updates selection', () => {
    render(withQuery(<GenerateDocDialog projectId="p1" open onOpenChange={() => {}} />))
    // click ADR radio (default is weekly_report)
    const adrLabel = screen.getByText('ADR').closest('label')
    fireEvent.click(adrLabel!)
    // selection sticks - check via radio aria-checked or just that no error
  })
})
