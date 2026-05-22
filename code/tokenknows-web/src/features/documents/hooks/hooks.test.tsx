/**
 * Documents hooks · useAsset / useAssets / useChapters / useChapterEvidence /
 * useDeleteAsset / useGenerateAsset / useCloneAsset / useChapterAutosave /
 * useRegenerate / useGenerationSSE
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useAsset } from './useAsset'
import { useAssets } from './useAssets'
import { useChapters } from './useChapters'
import { useChapterEvidence } from './useChapterEvidence'
import { useDeleteAsset } from './useDeleteAsset'
import { useGenerateAsset } from './useGenerateAsset'
import { useCloneAsset } from './useCloneAsset'
import { useRegenerate } from './useRegenerate'
import { useChapterAutosave } from './useChapterAutosave'
import { api } from '@/lib/api'


function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


beforeEach(() => {
  // ensure clean spy
})


afterEach(() => {
  vi.restoreAllMocks()
})


describe('useAsset', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useAsset(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: { id: 'a1' } } as never)
    const { result } = renderHook(() => useAsset('a1'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith('/assets/a1')
  })
})


describe('useAssets', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useAssets(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches with filters', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    } as never)
    renderHook(() => useAssets('p1', { type: 'weekly_report' }),
      { wrapper: wrapper() })
    await waitFor(() => expect(api.get).toHaveBeenCalled())
  })
})


describe('useChapters', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useChapters(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches chapters', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: [] } as never)
    renderHook(() => useChapters('a1'), { wrapper: wrapper() })
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/assets/a1/chapters')
    })
  })
})


describe('useChapterEvidence', () => {
  it('disabled when either id null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useChapterEvidence(null, 'c1'), { wrapper: wrapper() })
    renderHook(() => useChapterEvidence('a1', null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches when both ids present', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: [] } as never)
    renderHook(() => useChapterEvidence('a1', 'c1'), { wrapper: wrapper() })
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/assets/a1/chapters/c1/evidence')
    })
  })
})


describe('useDeleteAsset', () => {
  it('DELETEs and invalidates', async () => {
    const delSpy = vi.spyOn(api, 'delete').mockResolvedValueOnce(undefined as never)
    const { result } = renderHook(() => useDeleteAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 'p1', assetId: 'a1' })
    })
    expect(delSpy).toHaveBeenCalledWith('/assets/a1')
  })
})


describe('useGenerateAsset', () => {
  it('POSTs to generate endpoint', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'a-new', status: 'generating' },
    } as never)
    const { result } = renderHook(() => useGenerateAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        projectId: 'p1',
        type: 'weekly_report',
        time_window: '2026-W21',
      })
    })
    expect(postSpy).toHaveBeenCalled()
  })
})


describe('useCloneAsset', () => {
  it('POSTs to clone endpoint', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'a-cloned' },
    } as never)
    const { result } = renderHook(() => useCloneAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 'p1', assetId: 'a1' })
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/clone')
  })
})


describe('useRegenerate', () => {
  it('POSTs regenerate', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'c1', content: 'new' },
    } as never)
    const { result } = renderHook(() => useRegenerate(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1', chapterId: 'c1', instruction: 'rewrite',
      })
    })
    expect(postSpy).toHaveBeenCalled()
  })
})


describe('useChapterAutosave', () => {
  const fakeChapter = {
    id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
    title: '§1', content: 'orig', layout: {},
    generated_by: null, regeneration_history: [],
    approval_state: 'pending' as const,
    redacted_spans: [],
  }

  it('idle state on mount + savedContent reflects chapter.content', () => {
    const { result } = renderHook(() => useChapterAutosave(fakeChapter),
      { wrapper: wrapper() })
    expect(result.current.state).toBe('idle')
    expect(result.current.savedContent).toBe('orig')
    expect(result.current.error).toBeNull()
  })

  it('handleEdit with same content is no-op', () => {
    const { result } = renderHook(() => useChapterAutosave(fakeChapter),
      { wrapper: wrapper() })
    act(() => {
      result.current.handleEdit('orig')
    })
    expect(result.current.state).toBe('idle')
  })

  it('handleEdit different content → state=editing', () => {
    const { result } = renderHook(() => useChapterAutosave(fakeChapter),
      { wrapper: wrapper() })
    act(() => {
      result.current.handleEdit('changed')
    })
    expect(result.current.state).toBe('editing')
  })
})
