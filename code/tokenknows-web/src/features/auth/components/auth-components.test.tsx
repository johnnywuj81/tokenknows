/**
 * Auth components · AuthCard + PasswordInput.
 */

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AuthCard } from './AuthCard'
import { PasswordInput } from './PasswordInput'


describe('AuthCard', () => {
  it('renders title + children', () => {
    render(
      <AuthCard title="登录">
        <div>FORM BODY</div>
      </AuthCard>,
    )
    expect(screen.getByText('登录')).toBeInTheDocument()
    expect(screen.getByText('FORM BODY')).toBeInTheDocument()
    expect(screen.getByText('TokenKnows')).toBeInTheDocument()
  })

  it('description optional', () => {
    render(
      <AuthCard title="x" description="使用邮箱登录">
        <div>x</div>
      </AuthCard>,
    )
    expect(screen.getByText('使用邮箱登录')).toBeInTheDocument()
  })

  it('footer slot rendered', () => {
    render(
      <AuthCard title="x" footer={<a href="/register">还没账号</a>}>
        <div>x</div>
      </AuthCard>,
    )
    expect(screen.getByText('还没账号')).toBeInTheDocument()
  })
})


describe('PasswordInput', () => {
  it('defaults to type=password', () => {
    render(<PasswordInput placeholder="pw" />)
    const input = screen.getByPlaceholderText('pw') as HTMLInputElement
    expect(input.type).toBe('password')
  })

  it('eye toggle switches to text', () => {
    render(<PasswordInput placeholder="pw" />)
    const input = screen.getByPlaceholderText('pw') as HTMLInputElement
    const toggle = screen.getByRole('button', { name: /显示密码/ })
    fireEvent.click(toggle)
    expect(input.type).toBe('text')
    // aria-label 切到 hide
    expect(screen.getByRole('button', { name: /隐藏密码/ })).toBeInTheDocument()
  })

  it('eye toggle twice → back to password', () => {
    render(<PasswordInput placeholder="pw" />)
    const input = screen.getByPlaceholderText('pw') as HTMLInputElement
    const toggle = screen.getByRole('button', { name: /显示密码/ })
    fireEvent.click(toggle)
    fireEvent.click(screen.getByRole('button', { name: /隐藏密码/ }))
    expect(input.type).toBe('password')
  })

  it('forwards ref', () => {
    let inputRef: HTMLInputElement | null = null
    render(
      <PasswordInput
        ref={(el) => { inputRef = el }}
        placeholder="pw"
      />,
    )
    expect(inputRef).not.toBeNull()
    expect(inputRef?.tagName).toBe('INPUT')
  })

  it('custom labels via props', () => {
    render(<PasswordInput showLabel="show" hideLabel="hide" placeholder="pw" />)
    expect(screen.getByRole('button', { name: 'show' })).toBeInTheDocument()
  })
})
