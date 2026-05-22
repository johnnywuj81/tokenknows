/**
 * useGenerationSSE · EventSource subscription with mocked SSE server.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useGenerationSSE } from './useGenerationSSE'


type Listener = (e: MessageEvent) => void

class FakeEventSource {
  url: string
  listeners: Record<string, Listener[]> = {}
  onerror: ((e: Event) => void) | null = null
  closed = false
  readyState = 0
  static instances: FakeEventSource[] = []

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(name: string, cb: Listener) {
    if (!this.listeners[name]) this.listeners[name] = []
    this.listeners[name].push(cb)
  }

  removeEventListener() {}

  dispatch(name: string, data: unknown) {
    const ev = new MessageEvent(name, { data: JSON.stringify(data) })
    this.listeners[name]?.forEach((cb) => cb(ev))
  }

  dispatchInvalidJson(name: string) {
    const ev = new MessageEvent(name, { data: '{not-json' })
    this.listeners[name]?.forEach((cb) => cb(ev))
  }

  close() {
    this.closed = true
    this.readyState = 2
  }
}


function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


describe('useGenerationSSE', () => {
  let originalES: typeof EventSource
  beforeEach(() => {
    originalES = globalThis.EventSource
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource
    FakeEventSource.instances = []
  })

  afterEach(() => {
    globalThis.EventSource = originalES
  })

  it('enabled=false: no EventSource opened', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: false }),
      { wrapper: createWrapper() },
    )
    expect(FakeEventSource.instances.length).toBe(0)
  })

  it('no assetId: no EventSource opened', () => {
    renderHook(
      () => useGenerationSSE({ assetId: null, enabled: true }),
      { wrapper: createWrapper() },
    )
    expect(FakeEventSource.instances.length).toBe(0)
  })

  it('opens EventSource on /api/v1/assets/:id/generation/stream', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a-x', enabled: true }),
      { wrapper: createWrapper() },
    )
    expect(FakeEventSource.instances.length).toBe(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/v1/assets/a-x/generation/stream')
  })

  it('dispatches snapshot event → onEvent receives parsed payload', () => {
    const onEvent = vi.fn()
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true, onEvent }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatch('snapshot', { stage: 'outline', progress: 0.2 })
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event: 'snapshot', stage: 'outline' }),
    )
  })

  it('invalid JSON: onEvent still called with bare event name (catch path)', () => {
    const onEvent = vi.fn()
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true, onEvent }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatchInvalidJson('snapshot')
    expect(onEvent).toHaveBeenCalledWith({ event: 'snapshot' })
  })

  it('chapter_completed: handler runs without crash', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatch('chapter_completed', { chapter_id: 'c1' })
    expect(es.closed).toBe(false)
  })

  it('stage_completed: handler runs', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatch('stage_completed', { stage: 'evidence' })
    es.dispatch('stage_started', { stage: 'assess' })
    expect(es.closed).toBe(false)
  })

  it('done event: EventSource closed', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatch('done', { status: 'completed' })
    expect(es.closed).toBe(true)
  })

  it('failed event: EventSource closed', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    es.dispatch('failed', { error: 'LLM timeout' })
    expect(es.closed).toBe(true)
  })

  it('unmount: EventSource closed in cleanup', () => {
    const { unmount } = renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    unmount()
    expect(es.closed).toBe(true)
  })

  it('onerror callback set (no-op)', () => {
    renderHook(
      () => useGenerationSSE({ assetId: 'a1', enabled: true }),
      { wrapper: createWrapper() },
    )
    const es = FakeEventSource.instances[0]
    expect(typeof es.onerror).toBe('function')
    es.onerror?.(new Event('error'))
  })
})
