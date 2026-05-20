/**
 * useResetPassword · 用 token 重置密码 mutation。
 */

import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface ResetPasswordPayload {
  token: string
  new_password: string
}

async function resetRequest(payload: ResetPasswordPayload): Promise<{ ok: boolean }> {
  const { data } = await api.post<{ ok: boolean }>('/auth/reset-password', payload)
  return data
}

export function useResetPassword() {
  return useMutation({
    mutationFn: resetRequest,
  })
}
