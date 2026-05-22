/**
 * RegenerateDialog · T08 章节重生成 dialog.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { RegenerateDialog } from './RegenerateDialog'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '本周亮点',
  content: '原内容',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


describe('RegenerateDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({
      regenerateOpen: false,
      regenerateChapterId: null,
    })
  })

  it('hidden when not open', () => {
    render(withQuery(<RegenerateDialog assetId="a1" />))
    expect(screen.queryByText('重生成章节')).toBeNull()
  })

  it('renders dialog with chapter title + model choices when open', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [mkChapter({ id: 'c1', order_index: 0, title: '本周亮点' })],
    })
    useDocumentUiStore.setState({
      regenerateOpen: true,
      regenerateChapterId: 'c1',
    })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('§1 本周亮点')).toBeInTheDocument())
    expect(screen.getByLabelText(/重生成指令/)).toBeInTheDocument()
    expect(screen.getByLabelText('模型')).toBeInTheDocument()
  })

  it('renders — when chapter not found', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    useDocumentUiStore.setState({
      regenerateOpen: true,
      regenerateChapterId: 'unknown',
    })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('—')).toBeInTheDocument())
  })

  it('submit disabled when instruction < 5 chars', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/重生成指令/), {
      target: { value: 'abc' },
    })
    expect(screen.getByText('提交重生成').closest('button')).toBeDisabled()
  })

  it('char counter updates', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/重生成指令/), {
      target: { value: 'hello world' },
    })
    expect(screen.getByText(/当前 11 字符/)).toBeInTheDocument()
  })

  it('successful submit POST + close dialog', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/重生成指令/), {
      target: { value: '用更简洁的语气重写' },
    })
    fireEvent.click(screen.getByText('提交重生成'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    await waitFor(() => expect(useDocumentUiStore.getState().regenerateOpen).toBe(false))
  })

  it('error displayed on submit failure', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    vi.spyOn(api, 'post').mockRejectedValue(new Error('LLM unavailable'))
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/重生成指令/), {
      target: { value: '用更简洁的语气重写' },
    })
    fireEvent.click(screen.getByText('提交重生成'))
    await waitFor(() => expect(screen.getByText(/LLM unavailable/)).toBeInTheDocument())
    // dialog should remain open
    expect(useDocumentUiStore.getState().regenerateOpen).toBe(true)
  })

  it('cancel button closes dialog', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('取消')).toBeInTheDocument())
    fireEvent.click(screen.getByText('取消'))
    await waitFor(() => expect(useDocumentUiStore.getState().regenerateOpen).toBe(false))
  })

  it('model select changes choice index', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    useDocumentUiStore.setState({ regenerateOpen: true, regenerateChapterId: 'c1' })
    render(withQuery(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByLabelText('模型')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('模型'), { target: { value: '1' } })
    expect((screen.getByLabelText('模型') as HTMLSelectElement).value).toBe('1')
  })
})
