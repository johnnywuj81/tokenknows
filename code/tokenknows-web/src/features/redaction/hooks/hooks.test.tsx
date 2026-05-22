/**
 * Redaction hooks · useRedactionScan / useTriggerRedactionScan /
 *                   useConfirmRedaction / useExemptRedaction.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  useRedactionScan,
  useTriggerRedactionScan,
  useConfirmRedaction,
  useExemptRedaction,
} from './useRedaction'
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


describe('useRedactionScan (query)', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useRedactionScan(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches scan job', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { job_id: 'j1', asset_id: 'a1', status: 'done', progress: 1.0, items: [] },
    } as never)
    const { result } = renderHook(() => useRedactionScan('a1'),
      { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('returns null on 404 (尚未扫描 is normal state)', async () => {
    vi.spyOn(api, 'get').mockRejectedValueOnce({
      code: 'NOT_FOUND', status: 404, message: '尚未扫描',
    })
    const { result } = renderHook(() => useRedactionScan('a1'),
      { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })
})


describe('useTriggerRedactionScan', () => {
  it('POST /assets/:id/redaction/scan', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { job_id: 'j1', asset_id: 'a1', status: 'done', progress: 1.0, items: [] },
    } as never)
    const { result } = renderHook(() => useTriggerRedactionScan(),
      { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync('a1')
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/redaction/scan')
  })
})


describe('useConfirmRedaction', () => {
  it('POST confirm with item_ids', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { items: [] },
    } as never)
    const { result } = renderHook(() => useConfirmRedaction(),
      { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1', itemIds: ['red-1', 'red-2'],
      })
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/assets/a1/redaction/confirm',
      { item_ids: ['red-1', 'red-2'] },
    )
  })
})


describe('useExemptRedaction', () => {
  it('POST exempt with item_id + reason', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { items: [] },
    } as never)
    const { result } = renderHook(() => useExemptRedaction(),
      { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1', itemId: 'red-1', reason: '示例数据',
      })
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/assets/a1/redaction/exempt',
      { item_id: 'red-1', reason: '示例数据' },
    )
  })
})
