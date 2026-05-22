/**
 * Auth secondary pages · VerifyEmail + ForgotPassword + ResetPassword.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import VerifyEmailPage from './VerifyEmailPage'
import ForgotPasswordPage from './ForgotPasswordPage'
import ResetPasswordPage from './ResetPasswordPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode, path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


// ─── VerifyEmailPage ─────────────────────────────────────


describe('VerifyEmailPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('no token: 链接无效', () => {
    render(withWrappers(<VerifyEmailPage />, '/verify-email'))
    expect(screen.getByText('链接无效')).toBeInTheDocument()
    expect(screen.getByText(/没有 \?token= 参数/)).toBeInTheDocument()
  })

  it('with token: pending state', () => {
    vi.spyOn(api, 'post').mockReturnValue(new Promise(() => {}))
    render(withWrappers(<VerifyEmailPage />, '/verify-email?token=abc'))
    expect(screen.getByText('正在验证...')).toBeInTheDocument()
    expect(screen.getByText('验证 token 中')).toBeInTheDocument()
  })

  it('success state', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    render(withWrappers(<VerifyEmailPage />, '/verify-email?token=ok'))
    await waitFor(() => expect(screen.getByText('邮箱已验证')).toBeInTheDocument())
    expect(screen.getByText('验证成功')).toBeInTheDocument()
  })

  it('error: specific ApiError message + code', async () => {
    const err = Object.assign(new Error('token 已过期'), { code: 'TOKEN_EXPIRED', status: 410 })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<VerifyEmailPage />, '/verify-email?token=expired'))
    await waitFor(() => expect(screen.getByText('验证失败')).toBeInTheDocument())
    expect(screen.getByText('token 已过期')).toBeInTheDocument()
    expect(screen.getByText(/错误码 · TOKEN_EXPIRED/)).toBeInTheDocument()
  })

  it('error: non-ApiError shows generic message', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('plain error'))
    render(withWrappers(<VerifyEmailPage />, '/verify-email?token=bad'))
    await waitFor(() => expect(screen.getByText('验证失败')).toBeInTheDocument())
    expect(screen.getByText('验证过程中发生错误')).toBeInTheDocument()
  })
})


// ─── ForgotPasswordPage ──────────────────────────────────


describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders form with email field', () => {
    render(withWrappers(<ForgotPasswordPage />, '/forgot-password'))
    expect(screen.getByText('找回密码')).toBeInTheDocument()
    expect(screen.getByLabelText('邮箱')).toBeInTheDocument()
  })

  it('zod: invalid email', async () => {
    render(withWrappers(<ForgotPasswordPage />, '/forgot-password'))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'bad' } })
    fireEvent.click(screen.getByText('发送重置链接'))
    await waitFor(() => expect(screen.getByText('请输入有效邮箱')).toBeInTheDocument())
  })

  it('success: 检查你的邮箱 state', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    render(withWrappers(<ForgotPasswordPage />, '/forgot-password'))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText('发送重置链接'))
    await waitFor(() => expect(screen.getByText('检查你的邮箱')).toBeInTheDocument())
    expect(screen.getByText('邮件已发送')).toBeInTheDocument()
  })

  it('error: ApiError banner', async () => {
    const err = Object.assign(new Error('请求过频'), { code: 'RATE_LIMITED', status: 429 })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<ForgotPasswordPage />, '/forgot-password'))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText('发送重置链接'))
    await waitFor(() => expect(screen.getByText('请求过频')).toBeInTheDocument())
  })
})


// ─── ResetPasswordPage ───────────────────────────────────


describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('no token: 链接无效', () => {
    render(withWrappers(<ResetPasswordPage />, '/reset-password'))
    expect(screen.getByText('链接无效')).toBeInTheDocument()
  })

  it('with token: renders form', () => {
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=abc'))
    expect(screen.getByText('设置新密码')).toBeInTheDocument()
    expect(screen.getByLabelText('新密码')).toBeInTheDocument()
    expect(screen.getByLabelText('再次输入')).toBeInTheDocument()
  })

  it('zod: password mismatch shows 两次输入不一致', async () => {
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=abc'))
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'Strong@1234' } })
    fireEvent.change(screen.getByLabelText('再次输入'), { target: { value: 'Different@5678' } })
    fireEvent.click(screen.getByText('重置密码'))
    await waitFor(() => expect(screen.getByText('两次输入不一致')).toBeInTheDocument())
  })

  it('success state: 密码已重置', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=abc'))
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'Strong@1234' } })
    fireEvent.change(screen.getByLabelText('再次输入'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByText('重置密码'))
    await waitFor(() => expect(screen.getByText('密码已重置')).toBeInTheDocument())
  })

  it('error: ApiError code displayed', async () => {
    const err = Object.assign(new Error('token 已使用'), { code: 'TOKEN_USED', status: 410 })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=used'))
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'Strong@1234' } })
    fireEvent.change(screen.getByLabelText('再次输入'), { target: { value: 'Strong@1234' } })
    fireEvent.click(screen.getByText('重置密码'))
    await waitFor(() => expect(screen.getByText('token 已使用')).toBeInTheDocument())
    expect(screen.getByText(/错误码 · TOKEN_USED/)).toBeInTheDocument()
  })
})
