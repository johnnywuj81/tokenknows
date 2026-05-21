/**
 * Placeholder 单测 · 施工占位组件 (W1D1 后, 各任务页未实现时使用).
 *
 * 依赖 react-router-dom Link, 用 MemoryRouter 包.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Placeholder } from './Placeholder'

function withRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('Placeholder', () => {
  it('renders task name + taskFile path', () => {
    withRouter(<Placeholder task="T01 · 登录" taskFile="T01-auth.md" />)
    expect(screen.getByText('T01 · 登录')).toBeInTheDocument()
    expect(screen.getByText(/T01-auth\.md/)).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    withRouter(
      <Placeholder
        task="T02"
        taskFile="T02.md"
        description="项目创建向导, 4 步骤 wizard"
      />,
    )
    expect(screen.getByText(/项目创建向导/)).toBeInTheDocument()
  })

  it('shows "施工占位" eyebrow tag', () => {
    withRouter(<Placeholder task="x" taskFile="x.md" />)
    expect(screen.getByText('施工占位')).toBeInTheDocument()
  })

  it('renders back link to /', () => {
    withRouter(<Placeholder task="x" taskFile="x.md" />)
    const link = screen.getByRole('link', { name: /返回工作台/ })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('href')).toBe('/')
  })
})
