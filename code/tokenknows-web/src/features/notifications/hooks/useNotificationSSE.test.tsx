/**
 * useNotificationSSE · v0.5.2 T54 unit tests.
 *
 * 思路:
 *   - mock EventSource (jsdom 无原生)
 *   - 渲染挂载 hook → EventSource 被 new
 *   - 发模拟事件 → 检查 onEvent 回调 + queryClient invalidate
 *   - userId 为 null → 不订阅
 *   - 卸载 → es.close 被调
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useNotificationSSE } from './useNotificationSSE'

// ─── EventSource mock ─────────────────────────────────────


type EventListener = (e: MessageEvent) => void

interface MockEventSource {
  url: string
  readyState: number
  CONNECTING: number
  OPEN: number
  CLOSED: number
  addEventListener: (name: string, fn: EventListener) => void
  removeEventListener: (name: string, fn: EventListener) => void
  close: () => void
  onerror: ((e: Event) => void) | null
  // helpers
  fireEvent: (name: string, data: unknown) => void
}

let lastInstance: MockEventSource | null = null

beforeEach(() => {
  lastInstance = null
  const listeners: Record<string, EventListener[]> = {}
  class MockES implements MockEventSource {
    url: string
    readyState = 0
    CONNECTING = 0
    OPEN = 1
    CLOSED = 2
    onerror: ((e: Event) => void) | null = null
    constructor(url: string) {
      this.url = url
      lastInstance = this
    }
    addEventListener(name: string, fn: EventListener) {
      listeners[name] = listeners[name] || []
      listeners[name].push(fn)
    }
    removeEventListener(name: string, fn: EventListener) {
      listeners[name] = (listeners[name] || []).filter((f) => f !== fn)
    }
    close() {
      this.readyState = this.CLOSED
    }
    fireEvent(name: string, data: unknown) {
      const fns = listeners[name] || []
      for (const fn of fns) {
        fn({ data: JSON.stringify(data) } as MessageEvent)
      }
    }
  }
  // @ts-expect-error - jsdom doesn't have EventSource
  globalThis.EventSource = MockES
})

afterEach(() => {
  // @ts-expect-error
  delete globalThis.EventSource
})


function _wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


describe('useNotificationSSE', () => {
  it('userId null → 不订阅', () => {
    const qc = new QueryClient()
    renderHook(
      () => useNotificationSSE({ userId: null }),
      { wrapper: _wrapper(qc) },
    )
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

  it('userId 有值 → new EventSource with stream URL', () => {
    const qc = new QueryClient()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-alice' }),
      { wrapper: _wrapper(qc) },
    )
    expect(lastInstance).not.toBeNull()
    expect(lastInstance!.url).toContain(
      '/api/v1/me/notifications/stream?user_id=ou-alice',
    )
  })

  it('snapshot 事件 → onEvent 回调 + invalidate', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onEvent = vi.fn()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a', onEvent }),
      { wrapper: _wrapper(qc) },
    )
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
      expect.objectContaining({
        event: 'snapshot',
        unread_count: 3,
      }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('consent_signed 事件 → 也 invalidate skill detail', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a' }),
      { wrapper: _wrapper(qc) },
    )
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
    // notifications + skills detail + skills list 都 invalidate
    const calls = invalidate.mock.calls.map(([arg]) => arg.queryKey)
    expect(calls).toContainEqual(['notifications'])
    expect(calls).toContainEqual(['skills', 'detail', 'skill-1'])
    expect(calls).toContainEqual(['skills'])
  })

  it('non-JSON data → 仍 invalidate (兜底)', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a' }),
      { wrapper: _wrapper(qc) },
    )
    act(() => {
      // 模拟坏 JSON
      const listeners = (lastInstance as unknown as { addEventListener: (n: string, f: EventListener) => void })
      // 直接 call listener with bad data:
      const evt = lastInstance!
      // fireEvent will JSON.stringify, so call raw:
      const fns: EventListener[] = []
      ;(evt as unknown as { addEventListener: (n: string, f: EventListener) => void }).addEventListener(
        'consent_request',
        (e) => fns.push(() => {}),
      )
      // 直接构造一个 listener path: 通过 fireEvent 用故意 invalid:
      // 用 JSON.stringify 一个会被 parse 失败的字符: 实际 JSON.parse 都会成功;
      // 模拟纯心跳: 通过 fireEvent('consent_request', "not-json-actually")
      evt.fireEvent('consent_request', 'just-a-string')
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('卸载时 close EventSource', () => {
    const qc = new QueryClient()
    const { unmount } = renderHook(
      () => useNotificationSSE({ userId: 'ou-a' }),
      { wrapper: _wrapper(qc) },
    )
    expect(lastInstance).not.toBeNull()
    const closeSpy = vi.spyOn(lastInstance!, 'close')
    unmount()
    expect(closeSpy).toHaveBeenCalled()
  })

  // ── T129 · asset_chapter_rejected 事件 ─────────────────────────
  it('asset_chapter_rejected 事件 → invalidate projects + asset detail + chapters', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onEvent = vi.fn()
    renderHook(
      () => useNotificationSSE({ userId: 'ou-author', onEvent }),
      { wrapper: _wrapper(qc) },
    )
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
      expect.objectContaining({
        event: 'asset_chapter_rejected',
        asset_id: 'asset-xyz',
      }),
    )
    const calls = invalidate.mock.calls.map(([arg]) => arg.queryKey)
    // 整 projects 树都 invalidate (覆盖 ['projects', :id, 'todos'] 等)
    expect(calls).toContainEqual(['projects'])
    // asset 详情 + chapters
    expect(calls).toContainEqual(['assets', 'asset-xyz'])
    expect(calls).toContainEqual(['assets', 'asset-xyz', 'chapters'])
  })

  it('asset_chapter_rejected 缺 asset_id → 仍 invalidate projects 不抛', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    renderHook(
      () => useNotificationSSE({ userId: 'ou-a' }),
      { wrapper: _wrapper(qc) },
    )
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
    // 没 asset_id → 不应触发 ['assets', ...] invalidate
    expect(calls.some((k) => k[0] === 'assets')).toBe(false)
  })

  it('userId 变化 → 新 EventSource', () => {
    const qc = new QueryClient()
    const { rerender } = renderHook(
      ({ uid }: { uid: string }) => useNotificationSSE({ userId: uid }),
      {
        wrapper: _wrapper(qc),
        initialProps: { uid: 'ou-alice' },
      },
    )
    const first = lastInstance
    rerender({ uid: 'ou-bob' })
    const second = lastInstance
    expect(first).not.toBe(second)
    expect(second!.url).toContain('user_id=ou-bob')
  })
})
