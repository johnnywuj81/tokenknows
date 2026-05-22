/**
 * Publish hooks · usePublishAsset + usePublishRecord + useAssetPublishRecords.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  usePublishAsset,
  usePublishRecord,
  useAssetPublishRecords,
} from './usePublish'
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


describe('usePublishAsset', () => {
  it('POST /assets/:id/publish with destinations/mode/visibility', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: [{ id: 'pub-1', destination: 'internal' }],
    } as never)
    const { result } = renderHook(() => usePublishAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1',
        destinations: ['internal'],
        publishMode: 'full',
        visibility: null,
      })
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/publish', {
      destinations: ['internal'],
      publish_mode: 'full',
      visibility: null,
    })
  })

  it('POST with multiple destinations + public link visibility', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: [],
    } as never)
    const { result } = renderHook(() => usePublishAsset(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        assetId: 'a1',
        destinations: ['internal', 'public_link'],
        publishMode: 'summary_with_backlink',
        visibility: 'public',
      })
    })
    expect(postSpy).toHaveBeenCalledWith('/assets/a1/publish', {
      destinations: ['internal', 'public_link'],
      publish_mode: 'summary_with_backlink',
      visibility: 'public',
    })
  })
})


describe('usePublishRecord', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => usePublishRecord(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches /publish-records/:id', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { id: 'pub-1' },
    } as never)
    const { result } = renderHook(() => usePublishRecord('pub-1'),
      { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith('/publish-records/pub-1')
  })
})


describe('useAssetPublishRecords', () => {
  it('disabled when null', () => {
    const getSpy = vi.spyOn(api, 'get')
    renderHook(() => useAssetPublishRecords(null), { wrapper: wrapper() })
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches /assets/:id/publish-records', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: [] } as never)
    renderHook(() => useAssetPublishRecords('a1'), { wrapper: wrapper() })
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/assets/a1/publish-records')
    })
  })
})
