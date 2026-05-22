/**
 * Review hooks · useApproveChapter / useRejectChapter / useSubmitAsset.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  useApproveChapter,
  useRejectChapter,
  useSubmitAsset,
} from './useReviewMutations'
import { api } from '@/lib/api'


function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


afterEach(() => {
  vi.restoreAllMocks()
})


describe('useApproveChapter', () => {
  it('POST approve chapter', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'c1', approval_state: 'approved' },
    } as never)
    const { result } = renderHook(() => useApproveChapter(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ assetId: 'a1', chapterId: 'c1' })
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/chapters/c1/approve')
  })
})


describe('useRejectChapter', () => {
  it('POST reject with reason', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'c1', approval_state: 'rejected' },
    } as never)
    const { result } = renderHook(() => useRejectChapter(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1', chapterId: 'c1', reason: '需要补充细节',
      })
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/assets/a1/chapters/c1/reject',
      { reason: '需要补充细节' },
    )
  })
})


describe('useSubmitAsset', () => {
  it('POST submit asset for review', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'a1', status: 'in_review' },
    } as never)
    const { result } = renderHook(() => useSubmitAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync('a1')
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/submit')
  })
})
