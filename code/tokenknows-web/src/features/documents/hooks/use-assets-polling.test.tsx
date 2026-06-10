/**
 * useAssets · 3s polling 分支测试 (generating 文档时启动 setInterval refetch).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useAssets } from './useAssets'
import { api } from '@/lib/api'


function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


describe('useAssets 3s polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('no generating: does not setInterval refetch', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [{
          id: 'a1', project_id: 'p1', type: 'weekly_report', title: 'done',
          status: 'draft', current_version: 1, template_id: null, created_by: 'u',
          approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
          created_at: '', updated_at: '',
        }],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    const { result } = renderHook(() => useAssets('p1'), { wrapper: createWrapper() })
    await vi.waitFor(() => expect(result.current.data).toBeDefined())
    const initialCalls = spy.mock.calls.length
    // advance 10s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    // no extra refetch
    expect(spy.mock.calls.length).toBe(initialCalls)
  })

  it('with generating: setInterval refetches', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [{
          id: 'a1', project_id: 'p1', type: 'weekly_report', title: 'generating',
          status: 'generating', current_version: 0, template_id: null, created_by: 'u',
          approval_state: 'pending', redaction_state: 'any_unresolved', metrics: null,
          created_at: '', updated_at: '',
        }],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    const { result } = renderHook(() => useAssets('p1'), { wrapper: createWrapper() })
    await vi.waitFor(() => expect(result.current.data).toBeDefined())
    const initialCalls = spy.mock.calls.length
    // advance 7s (>3s interval but <6s for safety)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000)
    })
    // should have polled at least once more
    expect(spy.mock.calls.length).toBeGreaterThan(initialCalls)
  })

  it('disabled when projectId null', () => {
    const spy = vi.spyOn(api, 'get')
    renderHook(() => useAssets(null), { wrapper: createWrapper() })
    expect(spy).not.toHaveBeenCalled()
  })

  it('applies type/status filters as query params', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    renderHook(() => useAssets('p1', { type: 'adr', status: 'approved' }), {
      wrapper: createWrapper(),
    })
    await vi.waitFor(() => expect(spy).toHaveBeenCalled())
    expect(spy.mock.calls[0][1]).toMatchObject({
      params: expect.objectContaining({ type: 'adr', status: 'approved' }),
    })
  })
})
