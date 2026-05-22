/**
 * LoginPage · 补足分支: password zod error display + 登录中... pending.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import LoginPage from './LoginPage'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/login']}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('LoginPage extra branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
  })

  it('zod: empty password shows 请输入密码', async () => {
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    // password 留空
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() => expect(screen.getByText('请输入密码')).toBeInTheDocument())
  })

  it('pending state: button shows 登录中... + disabled', async () => {
    let resolveFn: ((v: unknown) => void) | null = null
    vi.spyOn(api, 'post').mockReturnValue(
      new Promise((res) => { resolveFn = res }),
    )
    render(withWrappers(<LoginPage />))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('登录'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /登录中/ })).toBeDisabled(),
    )
    // resolve so pending mutation cleans up
    resolveFn!({ data: { access_token: 't', refresh_token: 'r', user: { id: 'u', email: 'a@b.com', display_name: 'A', role: 'editor' } } })
  })
})
