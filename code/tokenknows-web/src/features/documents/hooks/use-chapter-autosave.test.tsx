/**
 * useChapterAutosave · debounce 2s + state machine + localStorage fallback.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useChapterAutosave } from './useChapterAutosave'
import { api } from '@/lib/api'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: 'T', content: '初始', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '', ...overrides,
})


function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


// Use real timers (much simpler than dealing with vi fake-timer/promise interaction).
// debounce 2s tests are slower but reliable.
describe('useChapterAutosave', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    try { localStorage.clear() } catch { /* ignore */ }
  })

  it('initial state: idle + savedContent = chapter.content', () => {
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    expect(result.current.state).toBe('idle')
    expect(result.current.savedContent).toBe('初始')
    expect(result.current.error).toBeNull()
  })

  it('handleEdit with same content: no state change', () => {
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('初始') })
    expect(result.current.state).toBe('idle')
  })

  it('handleEdit with new content: state=editing', () => {
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('新内容') })
    expect(result.current.state).toBe('editing')
  })

  it('after 2s debounce: state=saving then saved', async () => {
    vi.spyOn(api, 'patch').mockResolvedValue({
      data: mkChapter({ content: '新内容' }),
    })
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('新内容') })
    await new Promise((r) => setTimeout(r, 2100))
    await waitFor(() => expect(result.current.state).toBe('saved'))
    expect(result.current.savedContent).toBe('新内容')
  })

  it('idle after 1.5s in saved state', async () => {
    vi.spyOn(api, 'patch').mockResolvedValue({ data: mkChapter({ content: '新' }) })
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('新') })
    await new Promise((r) => setTimeout(r, 2100))
    await waitFor(() => expect(result.current.state).toBe('saved'))
    await new Promise((r) => setTimeout(r, 1600))
    expect(result.current.state).toBe('idle')
  })

  it('save error: state=error + localStorage fallback', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    const apiErr = Object.assign(new Error('保存失败'), { code: 'SERVER_ERROR', status: 500 })
    vi.spyOn(api, 'patch').mockRejectedValue(apiErr)
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('草稿') })
    await new Promise((r) => setTimeout(r, 2100))
    await waitFor(() => expect(result.current.state).toBe('error'))
    expect(result.current.error).toBe('保存失败')
    expect(setItemSpy).toHaveBeenCalledWith('tokenknows_draft_c1', '草稿')
  })

  it('save error with non-ApiError: fallback message "保存失败"', async () => {
    vi.spyOn(api, 'patch').mockRejectedValue(new Error('raw error'))
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('x') })
    await new Promise((r) => setTimeout(r, 2100))
    await waitFor(() => expect(result.current.state).toBe('error'))
    expect(result.current.error).toBe('保存失败')
  })

  it('successful save clears localStorage', async () => {
    const removeSpy = vi.spyOn(Storage.prototype, 'removeItem')
    vi.spyOn(api, 'patch').mockResolvedValue({ data: mkChapter({ content: '新' }) })
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('新') })
    await new Promise((r) => setTimeout(r, 2100))
    await waitFor(() => expect(removeSpy).toHaveBeenCalledWith('tokenknows_draft_c1'))
  })

  it('rapid edits: only last triggers save (debounce)', async () => {
    const patchSpy = vi.spyOn(api, 'patch').mockResolvedValue({
      data: mkChapter({ content: 'final' }),
    })
    const { result } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => {
      result.current.handleEdit('v1')
      result.current.handleEdit('v2')
      result.current.handleEdit('v3')
    })
    await new Promise((r) => setTimeout(r, 2100))
    expect(patchSpy).toHaveBeenCalledTimes(1)
    expect(patchSpy.mock.calls[0][1]).toEqual({ content: 'v3' })
  })

  it('unmount cleans up timers (no error)', () => {
    const { result, unmount } = renderHook(() => useChapterAutosave(mkChapter()), {
      wrapper: createWrapper(),
    })
    act(() => { result.current.handleEdit('x') })
    unmount()
    // No error, no save attempted
  })
})
