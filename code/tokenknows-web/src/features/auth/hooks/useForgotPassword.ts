/**
 * useForgotPassword · 发送找回密码邮件 mutation。
 */

import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface ForgotResponse {
  ok: boolean
  message: string
}

async function forgotRequest(email: string): Promise<ForgotResponse> {
  const { data } = await api.post<ForgotResponse>('/auth/forgot-password', { email })
  return data
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: forgotRequest,
  })
}
