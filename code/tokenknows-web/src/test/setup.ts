/**
 * Vitest setup · jest-dom matchers + 全局 DOM cleanup.
 *
 * 自动跑在每个 test 文件前 (vitest.config.ts setupFiles).
 */

import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个 test 后清理 DOM, 防止跨文件污染
afterEach(() => {
  cleanup()
})

// Polyfills for jsdom (Radix UI uses these)
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (typeof globalThis.IntersectionObserver === 'undefined') {
  globalThis.IntersectionObserver = class IntersectionObserver {
    root = null
    rootMargin = ''
    thresholds: readonly number[] = []
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
  } as unknown as typeof IntersectionObserver
}

// scrollIntoView (Radix Tabs uses)
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn() as unknown as Element['scrollIntoView']
}

// PointerEvent capture (Radix Select)
if (typeof Element !== 'undefined' && !Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = vi.fn(() => false) as unknown as Element['hasPointerCapture']
  Element.prototype.releasePointerCapture = vi.fn() as unknown as Element['releasePointerCapture']
  Element.prototype.setPointerCapture = vi.fn() as unknown as Element['setPointerCapture']
}

// elementFromPoint (TipTap ≥3.26 Placeholder viewport tracking 调用,
// jsdom 未实现; prosemirror posAtCoords 对 null 有兜底, 返回 null 即可)
if (typeof Document !== 'undefined' && !Document.prototype.elementFromPoint) {
  Document.prototype.elementFromPoint = vi.fn(() => null) as unknown as Document['elementFromPoint']
}

// EventSource polyfill (SSE clients in DocumentPage)
if (typeof globalThis.EventSource === 'undefined') {
  globalThis.EventSource = class EventSource {
    url: string
    readyState = 0
    onopen: ((this: EventSource, ev: Event) => void) | null = null
    onmessage: ((this: EventSource, ev: MessageEvent) => void) | null = null
    onerror: ((this: EventSource, ev: Event) => void) | null = null
    static readonly CONNECTING = 0
    static readonly OPEN = 1
    static readonly CLOSED = 2
    constructor(url: string) { this.url = url }
    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() { return true }
    close() { this.readyState = 2 }
  } as unknown as typeof EventSource
}
