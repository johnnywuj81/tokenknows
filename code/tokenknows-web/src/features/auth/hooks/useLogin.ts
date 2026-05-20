/**
 * useLogin · 登录 mutation,成功后写入 authStore。
 */

import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { LoginRequest, LoginResponse } from '@/types/api'

async function loginRequest(payload: LoginRequest): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login', payload)
  return data
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth)

  return useMutation({
    mutationFn: loginRequest,
    onSuccess: (response) => {
      setAuth(response.user, response.access_token)
    },
  })
}
