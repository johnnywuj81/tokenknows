/**
 * LoadingSkeleton 单测 · 6 种 variant 渲染 + a11y.
 *
 * 不深入测每个骨架结构的像素, 只验证:
 *   1. 每个 variant 都能渲染不崩
 *   2. a11y: aria-busy + aria-live (屏幕阅读器关心)
 *   3. 自定义 className 透传
 *   4. 不同 variant 渲染出不同数量的 Skeleton 块 (区分度)
 */

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { LoadingSkeleton } from './LoadingSkeleton'

const VARIANTS = ['workbench', 'list', 'document', 'form', 'drawer', 'card'] as const

describe('LoadingSkeleton', () => {
  it.each(VARIANTS)('renders %s variant without crashing', (variant) => {
    const { container } = render(<LoadingSkeleton variant={variant} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it.each(VARIANTS)('%s variant has aria-busy=true', (variant) => {
    const { container } = render(<LoadingSkeleton variant={variant} />)
    const root = container.firstChild as HTMLElement
    expect(root.getAttribute('aria-busy')).toBe('true')
  })

  it.each(VARIANTS)('%s variant has aria-live=polite', (variant) => {
    const { container } = render(<LoadingSkeleton variant={variant} />)
    const root = container.firstChild as HTMLElement
    expect(root.getAttribute('aria-live')).toBe('polite')
  })

  it('applies custom className', () => {
    const { container } = render(
      <LoadingSkeleton variant="card" className="my-loading" />,
    )
    expect(container.firstChild).toHaveClass('my-loading')
  })

  it('card variant renders fewer Skeleton blocks than workbench (区分度)', () => {
    // shadcn Skeleton 渲染为 <div class="animate-pulse ...">, 用 class 数子节点
    const cardR = render(<LoadingSkeleton variant="card" />)
    const cardBlocks = cardR.container.querySelectorAll('.animate-pulse').length
    cardR.unmount()

    const wbR = render(<LoadingSkeleton variant="workbench" />)
    const wbBlocks = wbR.container.querySelectorAll('.animate-pulse').length
    wbR.unmount()

    // workbench 有 ~17 个 skeleton 块, card 只有 3 个
    expect(cardBlocks).toBeLessThan(wbBlocks)
    expect(cardBlocks).toBeGreaterThan(0)
    expect(wbBlocks).toBeGreaterThan(10)
  })

  it('fade-in animation class applied', () => {
    const { container } = render(<LoadingSkeleton variant="card" />)
    const root = container.firstChild as HTMLElement
    expect(root.className).toMatch(/fade-in/)
  })
})
