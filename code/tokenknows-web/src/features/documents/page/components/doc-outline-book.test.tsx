/**
 * DocOutline · v0.2 book nested rendering
 *
 * 当 chapters 含 depth>0 或 parent_id 时, 切到嵌套渲染:
 *   - 顶层显示「卷」, 下面缩进展示该卷内的「章」
 *   - 卷可折叠 (chevron 切换)
 *   - 单击章 触发滚动
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DocOutline } from './DocOutline'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter>): Chapter => ({
  id: 'x',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: 'x',
  content: '',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  redacted_spans: [],
  ...overrides,
})


describe('DocOutline · book nested rendering', () => {
  let originalIO: typeof IntersectionObserver
  let originalRAF: typeof requestAnimationFrame

  beforeEach(() => {
    originalIO = globalThis.IntersectionObserver
    originalRAF = globalThis.requestAnimationFrame
    // 关闭 IO 的实际效果
    globalThis.IntersectionObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() { return [] }
      root = null
      rootMargin = ''
      thresholds = []
    } as unknown as typeof IntersectionObserver
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    }) as typeof requestAnimationFrame
  })

  afterEach(() => {
    globalThis.IntersectionObserver = originalIO
    globalThis.requestAnimationFrame = originalRAF
  })

  function renderBookOutline() {
    const chapters: Chapter[] = [
      mkChapter({ id: 'v1', title: '卷一 · 概述', depth: 0, parent_id: null, order_index: 0 }),
      mkChapter({ id: 'v1-c1', title: '第一章 · 背景', depth: 1, parent_id: 'v1', order_index: 1 }),
      mkChapter({ id: 'v1-c2', title: '第二章 · 概念', depth: 1, parent_id: 'v1', order_index: 2 }),
      mkChapter({ id: 'v2', title: '卷二 · 实现', depth: 0, parent_id: null, order_index: 3 }),
      mkChapter({ id: 'v2-c1', title: '第一章 · 架构', depth: 1, parent_id: 'v2', order_index: 4 }),
    ]
    const scrollRef = { current: document.createElement('div') }
    return render(<DocOutline chapters={chapters} scrollRef={scrollRef} />)
  }

  it('renders volumes and child chapters with hierarchy', () => {
    renderBookOutline()
    // 顶部 summary 出现 "2 卷"
    expect(screen.getByText(/书籍大纲/)).toBeInTheDocument()
    expect(screen.getByText(/2 卷/)).toBeInTheDocument()
    expect(screen.getByText(/3 章/)).toBeInTheDocument()
    // 卷与章都被渲染
    expect(screen.getByText('卷一 · 概述')).toBeInTheDocument()
    expect(screen.getByText('卷二 · 实现')).toBeInTheDocument()
    expect(screen.getByText('第一章 · 背景')).toBeInTheDocument()
    expect(screen.getByText('第一章 · 架构')).toBeInTheDocument()
  })

  it('collapses a volume hiding its child chapters when chevron clicked', () => {
    renderBookOutline()
    // 折叠卷一
    const collapseBtn = screen.getAllByRole('button', { name: /折叠本卷|展开本卷/ })[0]
    fireEvent.click(collapseBtn)
    // 卷一的章应消失, 卷二的章仍在
    expect(screen.queryByText('第一章 · 背景')).not.toBeInTheDocument()
    expect(screen.queryByText('第二章 · 概念')).not.toBeInTheDocument()
    expect(screen.getByText('第一章 · 架构')).toBeInTheDocument()
  })

  it('clicking a chapter scrolls anchor into view', () => {
    renderBookOutline()
    // 给目标 chapter anchor 准备 DOM
    const anchor = document.createElement('div')
    anchor.id = 'chapter-anchor-v1-c2'
    document.body.appendChild(anchor)
    const scrollIntoView = vi.fn()
    anchor.scrollIntoView = scrollIntoView

    fireEvent.click(screen.getByText('第二章 · 概念'))
    expect(scrollIntoView).toHaveBeenCalled()

    document.body.removeChild(anchor)
  })

  it('renders flat outline for 4 legacy doc types (no depth/parent_id)', () => {
    const flat: Chapter[] = [
      mkChapter({ id: 'c1', title: '本周进展', order_index: 0 }),
      mkChapter({ id: 'c2', title: 'Bug 与解决', order_index: 1 }),
    ]
    const scrollRef = { current: document.createElement('div') }
    render(<DocOutline chapters={flat} scrollRef={scrollRef} />)
    // 显示扁平 "大纲 · 2 章" 而非 "书籍大纲"
    expect(screen.getByText(/大纲 · 2 章/)).toBeInTheDocument()
    expect(screen.queryByText(/书籍大纲/)).not.toBeInTheDocument()
  })
})
