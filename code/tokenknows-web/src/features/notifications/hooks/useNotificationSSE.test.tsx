/**
 * useNotificationSSE · v0.5.2 T54 / T132 unit tests.
 *
 * 思路:
 *   - mock @microsoft/fetch-event-source (替代 v1.0 原生 EventSource mock)
 *   - 渲染挂载 hook → fetchEventSource 被调
 *   - 通过捕获的 opts.onmessage 模拟 SSE 事件 → 检查 onEvent 回调 + queryClient invalidate
 *   - userId 为 null → 不订阅
 *   - 卸载 → signal aborted
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useNotificationSSE } from './useNotificationSSE'

// ─── fetchEventSource mock ────────────────────────────────

interface FakeInstance {
  url: string
  signal: AbortSignal
  onmessage: (ev: { event: string; data: string; id?: string }) => void
  onopen?: (resp: Response) => Promise<void>
  onerror?: (err: unknown) => number | void
  fireEvent: (eventName: string, data: unknown) => void
}

let lastInstance: FakeInstance | null = null

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn(async (url: string, opts: Record<string, unknown>) => {
    const instance: FakeInstance = {
      url,
      signal: opts.signal as AbortSignal,
      onmessage: opts.onmessage as FakeInstance['onmessage'],
      onopen: opts.onopen as FakeInstance['onopen'],
      onerror: opts.onerror as FakeInstance['onerror'],
      fireEvent(eventName, data) {
        this.onmessage({
          event: eventName,
          data: typeof data === 'string' ? data : JSON.stringify(data),
        })
      },
    }
    lastInstance = instance
    // 模拟成功 onopen
    if (instance.onopen) {
      const fakeResp = new Response(null, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      })
      await instance.onopen(fakeResp)
    }
  }),
}))

beforeEach(() => {
  lastInstance = null
})

afterEach(() => {
  vi.clearAllMocks()
})

function _wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useNotificationSSE', () => {
  it('userId null → 不订阅', () => {
    const qc = new QueryClient()
    renderHook(() => useNotificationSSE({ userId: null }), { wrapper: _wrapper(qc) })
    expect(lastInstance).toBeNull()
  })

  it('enabled false → 不订阅', () => {
    const qc = new QueryClient()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a', enabled: false }),
      { wrapper: _wrapper(qc) },
    )
    expect(lastInstance).toBeNull()
  })

  it('userId 有值 → fetchEventSource 用 stream URL 调起', async () => {
    const qc = new QueryClient()
    renderHook(() => useNotificationSSE({ userId: 'ou-alice' }), { wrapper: _wrapper(qc) })
    // fetchEventSource 是 async, 让 microtask 跑完
    await act(async () => { await Promise.resolve() })
    expect(lastInstance).not.toBeNull()
    expect(lastInstance!.url).toContain('/api/v1/me/notifications/stream?user_id=ou-alice')
  })

  it('snapshot 事件 → onEvent 回调 + invalidate', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onEvent = vi.fn()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a', onEvent }),
      { wrapper: _wrapper(qc) },
    )
    await act(async () => { await Promise.resolve() })
    act(() => {
      lastInstance!.fireEvent('snapshot', {
        user_id: 'ou-a',
        skill_id: null,
        notification_id: null,
        unread_count: 3,
        extra: {},
        timestamp: '2026-05-23T13:00:00Z',
      })
    })
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event: 'snapshot', unread_count: 3 }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('consent_signed 事件 → 也 invalidate skill detail', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(() => useNotificationSSE({ userId: 'ou-a' }), { wrapper: _wrapper(qc) })
    await act(async () => { await Promise.resolve() })
    act(() => {
      lastInstance!.fireEvent('consent_signed', {
        user_id: 'ou-a',
        skill_id: 'skill-1',
        notification_id: 'n-1',
        unread_count: 2,
        extra: { actor_user_id: 'ou-b' },
        timestamp: '2026-05-23',
      })
    })
    const calls = invalidate.mock.calls.map(([arg]) => arg.queryKey)
    expect(calls).toContainEqual(['notifications'])
    expect(calls).toContainEqual(['skills', 'detail', 'skill-1'])
    expect(calls).toContainEqual(['skills'])
  })

  it('non-JSON data → 仍 invalidate notifications (兜底)', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(() => useNotificationSSE({ userId: 'ou-a' }), { wrapper: _wrapper(qc) })
    await act(async () => { await Promise.resolve() })
    act(() => {
      // fireEvent('consent_request', 'just-a-string') 不会被 JSON.stringify,
      // 直接 push 一个非 JSON data:
      lastInstance!.onmessage({ event: 'consent_request', data: 'not-json-{' })
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('未知事件名 (如 heartbeat) → 不调 onEvent / 不 invalidate', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onEvent = vi.fn()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a', onEvent }),
      { wrapper: _wrapper(qc) },
    )
    await act(async () => { await Promise.resolve() })
    act(() => {
      lastInstance!.onmessage({ event: 'heartbeat', data: '' })
    })
    expect(onEvent).not.toHaveBeenCalled()
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('卸载时 abort signal', async () => {
    const qc = new QueryClient()
    const { unmount } = renderHook(
      () => useNotificationSSE({ userId: 'ou-a' }),
      { wrapper: _wrapper(qc) },
    )
    await act(async () => { await Promise.resolve() })
    expect(lastInstance).not.toBeNull()
    expect(lastInstance!.signal.aborted).toBe(false)
    unmount()
    expect(lastInstance!.signal.aborted).toBe(true)
  })

  // ── T129 · asset_chapter_rejected 事件 ─────────────────────────
  it('asset_chapter_rejected 事件 → invalidate projects + asset detail + chapters', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onEvent = vi.fn()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-author', onEvent }),
      { wrapper: _wrapper(qc) },
    )
    await act(async () => { await Promise.resolve() })
    act(() => {
      lastInstance!.fireEvent('asset_chapter_rejected', {
        user_id: 'ou-author',
        skill_id: null,
        asset_id: 'asset-xyz',
        notification_id: null,
        unread_count: null,
        extra: {
          chapter_id: 'c4',
          chapter_title: '风险与阻塞',
          order_index: 3,
          reason: '风险评估不够具体',
          project_id: 'proj-demo-001',
        },
        timestamp: '2026-05-24T03:30:00Z',
      })
    })
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event: 'asset_chapter_rejected', asset_id: 'asset-xyz' }),
    )
    const calls = invalidate.mock.calls.map(([arg]) => arg.queryKey)
    expect(calls).toContainEqual(['projects'])
    expect(calls).toContainEqual(['assets', 'asset-xyz'])
    expect(calls).toContainEqual(['assets', 'asset-xyz', 'chapters'])
  })

  it('asset_chapter_rejected 缺 asset_id → 仍 invalidate projects 不抛', async () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(() => useNotificationSSE({ userId: 'ou-a' }), { wrapper: _wrapper(qc) })
    await act(async () => { await Promise.resolve() })
    act(() => {
      lastInstance!.fireEvent('asset_chapter_rejected', {
        user_id: 'ou-a',
        skill_id: null,
        asset_id: null,
        notification_id: null,
        unread_count: null,
        extra: {},
        timestamp: '',
      })
    })
    const calls = invalidate.mock.calls.map(([arg]) => arg.queryKey)
    expect(calls).toContainEqual(['projects'])
    expect(calls.some((k) => k[0] === 'assets')).toBe(false)
  })

  it('userId 变化 → 新连接 (abort 旧 + 启新)', async () => {
    const qc = new QueryClient()
    const { rerender } = renderHook(
      ({ uid }: { uid: string }) => useNotificationSSE({ userId: uid }),
      { wrapper: _wrapper(qc), initialProps: { uid: 'ou-alice' } },
    )
    await act(async () => { await Promise.resolve() })
    const first = lastInstance
    rerender({ uid: 'ou-bob' })
    await act(async () => { await Promise.resolve() })
    const second = lastInstance
    expect(first).not.toBe(second)
    expect(first!.signal.aborted).toBe(true)
    expect(second!.url).toContain('user_id=ou-bob')
  })
})
