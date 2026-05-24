/**
 * T135 · useTodos polling 兜底.
 *
 * 验证:
 *  - id 缺失 → disabled, 不发请求
 *  - id 有值 → 首发请求成功
 *  - 60s 后自动 refetch (兜底 SSE 断连)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTodos } from './useTodos'
import { api } from '@/lib/api'


function _wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


describe('useTodos · T135 polling', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('id=null → disabled, 不调 api', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    renderHook(() => useTodos(null), {
      wrapper: _wrapper(new QueryClient({ defaultOptions: { queries: { retry: false } } })),
    })
    // 给一点时间, 即便有 setTimeout 也不该触发
    await vi.advanceTimersByTimeAsync(100)
    expect(get).not.toHaveBeenCalled()
  })

  it('id 有值 → 首发请求并返回数据', async () => {
    const get = vi
      .spyOn(api, 'get')
      .mockResolvedValue({ data: [{ id: 't1', type: 'pending_review', title: 'x', due_at: null, created_at: '' }] })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTodos('p1'), { wrapper: _wrapper(qc) })
    await waitFor(() => expect(result.current.data?.length).toBe(1))
    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/projects/p1/todos')
  })

  it('60s 后自动 refetch (polling 兜底)', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTodos('p1'), { wrapper: _wrapper(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(get).toHaveBeenCalledTimes(1)

    // 推 60s, 应触发第 2 次拉
    await vi.advanceTimersByTimeAsync(60_000)
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))

    // 再推 60s, 第 3 次
    await vi.advanceTimersByTimeAsync(60_000)
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3))
  })
})
