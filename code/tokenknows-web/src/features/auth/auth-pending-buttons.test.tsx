/**
 * Forgot/Reset Password pages · pending spinner branches + Reset error code display.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import ForgotPasswordPage from './ForgotPasswordPage'
import ResetPasswordPage from './ResetPasswordPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode, path = '/forgot-password') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('ForgotPasswordPage pending', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows 发送中... while pending', async () => {
    // 初始化为 no-op 避免 TS 把闭包内赋值的变量窄化成 null (TS2349)
    let resolveFn: (v: unknown) => void = () => {}
    vi.spyOn(api, 'post').mockReturnValue(new Promise((res) => { resolveFn = res }))
    render(withWrappers(<ForgotPasswordPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByText('发送重置链接'))
    await waitFor(() => expect(screen.getByText(/发送中/)).toBeInTheDocument())
    resolveFn({ data: { ok: true } })
  })
})


describe('ResetPasswordPage pending + error code', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows 提交中... while pending', async () => {
    // 初始化为 no-op 避免 TS 把闭包内赋值的变量窄化成 null (TS2349)
    let resolveFn: (v: unknown) => void = () => {}
    vi.spyOn(api, 'post').mockReturnValue(new Promise((res) => { resolveFn = res }))
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=abc'))
    const pwInputs = document.querySelectorAll('input[type="password"]')
    fireEvent.change(pwInputs[0], { target: { value: 'StrongP@ss1' } })
    fireEvent.change(pwInputs[1], { target: { value: 'StrongP@ss1' } })
    fireEvent.click(screen.getByText('重置密码'))
    await waitFor(() => expect(screen.getByText(/提交中/)).toBeInTheDocument())
    resolveFn({ data: { ok: true } })
  })

  it('shows error code badge when ApiError', async () => {
    const apiErr = Object.assign(new Error('token 失效'), {
      code: 'TOKEN_EXPIRED', status: 400,
    })
    vi.spyOn(api, 'post').mockRejectedValue(apiErr)
    render(withWrappers(<ResetPasswordPage />, '/reset-password?token=abc'))
    const pwInputs = document.querySelectorAll('input[type="password"]')
    fireEvent.change(pwInputs[0], { target: { value: 'StrongP@ss1' } })
    fireEvent.change(pwInputs[1], { target: { value: 'StrongP@ss1' } })
    fireEvent.click(screen.getByText('重置密码'))
    await waitFor(() => expect(screen.getByText(/token 失效/)).toBeInTheDocument())
    expect(screen.getByText(/TOKEN_EXPIRED/)).toBeInTheDocument()
  })
})
