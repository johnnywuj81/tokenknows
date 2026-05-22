/**
 * Auth hooks 6 个全测.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useLogin } from './useLogin'
import { useRegister } from './useRegister'
import { useCurrentUser } from './useCurrentUser'
import { useVerifyEmail } from './useVerifyEmail'
import { useForgotPassword } from './useForgotPassword'
import { useResetPassword } from './useResetPassword'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types/api'


const mockUser: User = {
  id: 'u1', email: 'demo@x.com', display_name: 'Demo',
  is_instance_admin: false, email_verified_at: null,
  created_at: '', updated_at: '',
}


function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


beforeEach(() => {
  localStorage.clear()
  useAuthStore.getState().logout()
})


afterEach(() => {
  vi.restoreAllMocks()
})


describe('useLogin', () => {
  it('POSTs /auth/login and writes authStore on success', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { user: mockUser, access_token: 'tok-1', refresh_token: 'rt-1' },
    } as never)
    const { result } = renderHook(() => useLogin(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ email: 'a@b', password: 'x' })
    })
    expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'a@b', password: 'x' })
    const auth = useAuthStore.getState()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.accessToken).toBe('tok-1')
    expect(auth.user?.id).toBe('u1')
  })

  it('rejects on error', async () => {
    vi.spyOn(api, 'post').mockRejectedValueOnce(new Error('401'))
    const { result } = renderHook(() => useLogin(), { wrapper: wrapper() })
    await act(async () => {
      try {
        await result.current.mutateAsync({ email: 'a@b', password: 'x' })
      } catch {
        // expected
      }
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})


describe('useRegister', () => {
  it('POSTs /auth/register without writing authStore', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { user: mockUser, requires_verification: true },
    } as never)
    const { result } = renderHook(() => useRegister(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        email: 'a@b', password: 'x', display_name: 'demo',
      })
    })
    expect(api.post).toHaveBeenCalledWith('/auth/register', expect.any(Object))
    // 注册成功不自动登录
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})


describe('useCurrentUser', () => {
  it('disabled when not authenticated', () => {
    const getSpy = vi.spyOn(api, 'get')
    const { result } = renderHook(() => useCurrentUser(), { wrapper: wrapper() })
    expect(result.current.isLoading).toBe(false)
    expect(getSpy).not.toHaveBeenCalled()
  })

  it('fetches /me when authenticated', async () => {
    useAuthStore.getState().setAuth(mockUser, 'tok')
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { ...mockUser, display_name: 'Updated' },
    } as never)
    const { result } = renderHook(() => useCurrentUser(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith('/me')
    expect(useAuthStore.getState().user?.display_name).toBe('Updated')
  })
})


describe('useVerifyEmail', () => {
  it('POSTs token to /me/verify-email', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { ok: true, verified_at: '2026-05-22T00:00:00Z' },
    } as never)
    const { result } = renderHook(() => useVerifyEmail(), { wrapper: wrapper() })
    await act(async () => {
      const res = await result.current.mutateAsync('token-xyz')
      expect(res.ok).toBe(true)
    })
    expect(api.post).toHaveBeenCalledWith('/me/verify-email', { token: 'token-xyz' })
  })
})


describe('useForgotPassword', () => {
  it('POSTs email to /auth/forgot-password', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { ok: true, message: '邮件已发送' },
    } as never)
    const { result } = renderHook(() => useForgotPassword(), { wrapper: wrapper() })
    await act(async () => {
      const res = await result.current.mutateAsync('user@x.com')
      expect(res.ok).toBe(true)
    })
    expect(api.post).toHaveBeenCalledWith('/auth/forgot-password', { email: 'user@x.com' })
  })
})


describe('useResetPassword', () => {
  it('POSTs token + new_password to /auth/reset-password', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({ data: { ok: true } } as never)
    const { result } = renderHook(() => useResetPassword(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ token: 't', new_password: 'new-pw' })
    })
    expect(api.post).toHaveBeenCalledWith('/auth/reset-password',
      { token: 't', new_password: 'new-pw' })
  })
})
