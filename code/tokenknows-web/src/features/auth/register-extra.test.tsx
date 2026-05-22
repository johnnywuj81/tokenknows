/**
 * RegisterPage · 补足分支覆盖 (success state + resend + error).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import RegisterPage from './RegisterPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/register']}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('RegisterPage extra branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('zod: invalid email shows error', async () => {
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'bad' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText('请输入有效邮箱')).toBeInTheDocument())
  })

  it('zod: short password shows error', async () => {
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText(/密码至少 10 位/)).toBeInTheDocument())
  })

  it('zod: missing symbol → 需包含符号', async () => {
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'NoSymbol123' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText(/需包含符号/)).toBeInTheDocument())
  })

  it('zod: short display_name', async () => {
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'A' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText(/昵称至少 2 个字符/)).toBeInTheDocument())
  })

  it('success: transitions to 请检查邮箱 state', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { id: 'u1', email: 'new@b.com' },
    })
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'new@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'New User' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText('请检查邮箱')).toBeInTheDocument())
    expect(screen.getByText('注册成功,等待邮箱验证')).toBeInTheDocument()
  })

  it('success: 重新发送 button clickable', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: { id: 'u1', email: 'new@b.com' },
    })
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'new@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'New User' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText('重新发送')).toBeInTheDocument())
    postSpy.mockClear()
    fireEvent.click(screen.getByText('重新发送'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
  })

  it('api error: shows error banner', async () => {
    const err = Object.assign(new Error('邮箱已被注册'), {
      code: 'CONFLICT', status: 409,
    })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'dup@b.com' } })
    fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: 'Dup' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => expect(screen.getByText('邮箱已被注册')).toBeInTheDocument())
  })
})
