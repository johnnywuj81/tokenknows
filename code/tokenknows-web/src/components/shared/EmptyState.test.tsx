/**
 * EmptyState 单测 · 渲染分支 + action 回调.
 *
 * 选这个组件因为:
 *   1. 每屏的"空数据"占位必用
 *   2. 纯 presentational, 不需要 Router/Query 上下文
 *   3. 4 条分支 (icon / description / action / className) 覆盖完整
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders title only (minimal)', () => {
    render(<EmptyState title="还没有项目" />)
    expect(screen.getByText('还没有项目')).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    render(
      <EmptyState
        icon={<span data-testid="custom-icon">📁</span>}
        title="empty"
      />,
    )
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(
      <EmptyState
        title="标题"
        description="新建一个项目, 接入数据源后即可看到事件流"
      />,
    )
    expect(screen.getByText(/新建一个项目/)).toBeInTheDocument()
  })

  it('omits description when not provided (no empty <p>)', () => {
    const { container } = render(<EmptyState title="t" />)
    // 只有 h3 (title), 没有 p (description)
    expect(container.querySelector('p')).toBeNull()
  })

  it('action button calls onClick exactly once on click', () => {
    const onClick = vi.fn()
    render(
      <EmptyState
        title="empty"
        action={{ label: '+ 新建项目', onClick }}
      />,
    )
    const btn = screen.getByRole('button', { name: /新建项目/ })
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('does not render button when action absent', () => {
    render(<EmptyState title="x" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('applies custom className to root', () => {
    const { container } = render(
      <EmptyState title="t" className="custom-padding" />,
    )
    expect(container.firstChild).toHaveClass('custom-padding')
  })
})
