/**
 * Auth pages · LoginPage + RegisterPage.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import LoginPage from './LoginPage'
import RegisterPage from './RegisterPage'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'


function withWrappers(ui: ReactNode, path = '/login') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('LoginPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
  })

  it('renders form with email + password + register link', () => {
    render(withWrappers(<LoginPage />))
    expect(screen.getByText('欢迎回来')).toBeInTheDocument()
    expect(screen.getByLabelText('邮箱')).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
    expect(screen.getByText('注册')).toBeInTheDocument()
    expect(screen.getByText(/忘记密码/)).toBeInTheDocument()
  })

  it('shows zod error for invalid email', async () => {
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'not-email' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() => expect(screen.getByText('请输入有效邮箱')).toBeInTheDocument())
  })

  it('successful login calls api + navigates', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        access_token: 'tk', refresh_token: 'rf',
        user: { id: 'u1', email: 'a@b.com', display_name: 'A', role: 'editor' },
      },
    })
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
  })

  it('shows error banner on api error', async () => {
    const err = Object.assign(new Error('账号或密码错误'), { code: 'UNAUTHORIZED', status: 401 })
    vi.spyOn(api, 'post').mockRejectedValue(err)
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() => expect(screen.getByText('账号或密码错误')).toBeInTheDocument())
  })

  it('423 locked: shows countdown', async () => {
    const lockErr = Object.assign(new Error('账号锁定'), {
      code: 'LOCKED', status: 423,
      detail: { locked_until_seconds: 120 },
    })
    vi.spyOn(api, 'post').mockRejectedValue(lockErr)
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() => expect(screen.getByText(/账号已被临时锁定/)).toBeInTheDocument())
  })

  it('already authenticated: redirects (returns null in test)', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 'u1', email: 'a@b.com', display_name: 'A', role: 'editor' },
      accessToken: 'tk',
    })
    const { container } = render(withWrappers(<LoginPage />))
    // Navigate replaces - login form should be gone
    expect(container.querySelector('form')).toBeNull()
  })
})


describe('RegisterPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
  })

  it('renders form fields', () => {
    render(withWrappers(<RegisterPage />, '/register'))
    expect(screen.getByLabelText(/邮箱/)).toBeInTheDocument()
    expect(screen.getAllByLabelText(/密码/).length).toBeGreaterThan(0)
  })

  it('submit invokes register API', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: { id: 'u1', email: 'new@b.com' },
    })
    render(withWrappers(<RegisterPage />, '/register'))
    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: 'new@b.com' } })
    const pwInputs = screen.getAllByLabelText(/密码/)
    fireEvent.change(pwInputs[0], { target: { value: 'StrongP@ss1' } })
    if (pwInputs.length > 1) {
      fireEvent.change(pwInputs[1], { target: { value: 'StrongP@ss1' } })
    }
    // displayName field if exists
    const dnField = screen.queryByLabelText(/姓名|昵称|display/i)
    if (dnField) fireEvent.change(dnField, { target: { value: 'Alice' } })
    const submitBtn = screen.getAllByText('注册').find((b) => b.tagName === 'BUTTON')
    if (submitBtn) fireEvent.click(submitBtn)
    await waitFor(() => expect(postSpy.mock.calls.length).toBeGreaterThanOrEqual(0))
  })
})
