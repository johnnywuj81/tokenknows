/**
 * DocOutline · IntersectionObserver branch coverage.
 *
 * 用真实 IO mock 捕获 callback, 手动触发 entries → 验证 activeId 更新.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { DocOutline } from './DocOutline'
import type { Chapter } from '@/types/api'


type IOCallback = (entries: IntersectionObserverEntry[]) => void

interface MockIO {
  callback: IOCallback
  observed: Element[]
  options?: IntersectionObserverInit
}

let lastIO: MockIO | null = null


class FakeIntersectionObserver {
  callback: IOCallback
  observed: Element[] = []
  options?: IntersectionObserverInit
  constructor(cb: IOCallback, options?: IntersectionObserverInit) {
    this.callback = cb
    this.options = options
    // 测试桩需要把实例暴露给模块级变量, 供手动触发 entries
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    lastIO = this
  }
  observe(el: Element) { this.observed.push(el) }
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
}


const mkChapter = (id: string, title: string, order_index = 0): Chapter => ({
  id, asset_id: 'a1', asset_version: 1, order_index,
  title, content: '', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  redacted_spans: [],
  created_at: '', updated_at: '',
})


describe('DocOutline IntersectionObserver branch', () => {
  let originalIO: typeof IntersectionObserver
  let originalRAF: typeof requestAnimationFrame
  let originalCAF: typeof cancelAnimationFrame

  beforeEach(() => {
    originalIO = globalThis.IntersectionObserver
    originalRAF = globalThis.requestAnimationFrame
    originalCAF = globalThis.cancelAnimationFrame
    globalThis.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver
    // 让 requestAnimationFrame 立即同步执行
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    }) as typeof requestAnimationFrame
    globalThis.cancelAnimationFrame = (() => {}) as typeof cancelAnimationFrame
    lastIO = null
  })

  afterEach(() => {
    globalThis.IntersectionObserver = originalIO
    globalThis.requestAnimationFrame = originalRAF
    globalThis.cancelAnimationFrame = originalCAF
  })

  it('observes chapter anchors when scrollRef has element', () => {
    const ch = mkChapter('c1', '亮点', 0)
    const el = document.createElement('div')
    el.id = 'chapter-anchor-c1'
    document.body.appendChild(el)
    const scrollRef = { current: document.createElement('div') }
    try {
      render(<DocOutline chapters={[ch]} scrollRef={scrollRef} />)
      expect(lastIO).not.toBeNull()
      expect(lastIO!.observed.length).toBe(1)
    } finally {
      document.body.removeChild(el)
    }
  })

  it('IO callback: visible chapter sets activeId', () => {
    const ch1 = mkChapter('c1', '亮点', 0)
    const ch2 = mkChapter('c2', '风险', 1)
    const el1 = document.createElement('div')
    el1.id = 'chapter-anchor-c1'
    const el2 = document.createElement('div')
    el2.id = 'chapter-anchor-c2'
    document.body.appendChild(el1)
    document.body.appendChild(el2)
    const scrollRef = { current: document.createElement('div') }
    try {
      const { container } = render(<DocOutline chapters={[ch1, ch2]} scrollRef={scrollRef} />)
      expect(lastIO).not.toBeNull()
      // Fire IO callback - c2 entry as visible
      act(() => {
        lastIO!.callback([
          {
            target: el2,
            isIntersecting: true,
            boundingClientRect: { top: 50 } as DOMRectReadOnly,
          } as unknown as IntersectionObserverEntry,
        ])
      })
      // c2 should be active
      const active = container.querySelector('.bg-accent-primary-light')
      expect(active?.textContent).toContain('2. 风险')
    } finally {
      document.body.removeChild(el1)
      document.body.removeChild(el2)
    }
  })

  it('IO callback: no visible chapters does not crash', () => {
    const ch = mkChapter('c1', '章节', 0)
    const el = document.createElement('div')
    el.id = 'chapter-anchor-c1'
    document.body.appendChild(el)
    const scrollRef = { current: document.createElement('div') }
    try {
      render(<DocOutline chapters={[ch]} scrollRef={scrollRef} />)
      act(() => {
        lastIO!.callback([
          {
            target: el,
            isIntersecting: false,
            boundingClientRect: { top: 0 } as DOMRectReadOnly,
          } as unknown as IntersectionObserverEntry,
        ])
      })
      // No crash
    } finally {
      document.body.removeChild(el)
    }
  })

  it('scrollRef.current null: returns early without observer', () => {
    const ch = mkChapter('c1', 'x', 0)
    const scrollRef = { current: null }
    render(<DocOutline chapters={[ch]} scrollRef={scrollRef} />)
    expect(lastIO).toBeNull()
  })

  it('empty chapters: no observer setup', () => {
    const scrollRef = { current: document.createElement('div') }
    render(<DocOutline chapters={[]} scrollRef={scrollRef} />)
    expect(lastIO).toBeNull()
  })

  it('IO callback: multiple visible chapters pick topmost (smallest top)', () => {
    const ch1 = mkChapter('c1', '亮点', 0)
    const ch2 = mkChapter('c2', '风险', 1)
    const el1 = document.createElement('div')
    el1.id = 'chapter-anchor-c1'
    const el2 = document.createElement('div')
    el2.id = 'chapter-anchor-c2'
    document.body.appendChild(el1)
    document.body.appendChild(el2)
    const scrollRef = { current: document.createElement('div') }
    try {
      const { container } = render(<DocOutline chapters={[ch1, ch2]} scrollRef={scrollRef} />)
      act(() => {
        lastIO!.callback([
          {
            target: el2,
            isIntersecting: true,
            boundingClientRect: { top: 200 } as DOMRectReadOnly,
          } as unknown as IntersectionObserverEntry,
          {
            target: el1,
            isIntersecting: true,
            boundingClientRect: { top: 100 } as DOMRectReadOnly,
          } as unknown as IntersectionObserverEntry,
        ])
      })
      // c1 (top=100) is smaller → active
      const active = container.querySelector('.bg-accent-primary-light')
      expect(active?.textContent).toContain('1. 亮点')
    } finally {
      document.body.removeChild(el1)
      document.body.removeChild(el2)
    }
  })
})
