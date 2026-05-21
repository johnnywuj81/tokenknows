/**
 * ErrorState 单测 · getErrorMessage 错误归一 + retry 回调 + variant 切换.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ErrorState } from './ErrorState'

describe('ErrorState', () => {
  it('renders default title "加载失败"', () => {
    render(<ErrorState />)
    expect(screen.getByText('加载失败')).toBeInTheDocument()
  })

  it('renders custom title', () => {
    render(<ErrorState title="项目加载失败" />)
    expect(screen.getByText('项目加载失败')).toBeInTheDocument()
  })

  it('extracts message from Error instance', () => {
    render(<ErrorState error={new Error('network blip')} />)
    expect(screen.getByText('network blip')).toBeInTheDocument()
  })

  it('extracts message from string', () => {
    render(<ErrorState error="connection refused" />)
    expect(screen.getByText('connection refused')).toBeInTheDocument()
  })

  it('extracts message from {message: ...} shape', () => {
    render(<ErrorState error={{ message: '后端 503' }} />)
    expect(screen.getByText('后端 503')).toBeInTheDocument()
  })

  it('falls back to "未知错误" for unrecognizable shapes', () => {
    render(<ErrorState error={42} />)
    expect(screen.getByText('未知错误')).toBeInTheDocument()
  })

  it('retry button calls onRetry exactly once', () => {
    const onRetry = vi.fn()
    render(<ErrorState onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: /重试/ }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('no retry button when onRetry absent', () => {
    render(<ErrorState />)
    expect(screen.queryByRole('button', { name: /重试/ })).toBeNull()
  })

  it('fullscreen variant adds min-h class', () => {
    const { container } = render(<ErrorState variant="fullscreen" />)
    const root = container.firstChild as HTMLElement
    expect(root.className).toContain('min-h-')
  })

  it('renders custom action node alongside retry', () => {
    render(
      <ErrorState
        onRetry={() => {}}
        action={<a href="/login">去登录</a>}
      />,
    )
    expect(screen.getByText('去登录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument()
  })

  it('role=alert for a11y', () => {
    const { container } = render(<ErrorState />)
    const root = container.firstChild as HTMLElement
    expect(root.getAttribute('role')).toBe('alert')
  })
})
