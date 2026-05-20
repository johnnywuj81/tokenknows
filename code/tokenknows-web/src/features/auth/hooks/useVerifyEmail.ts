/**
 * useVerifyEmail · 邮箱验证 mutation。
 * URL ?token=xxx 在 Page 挂载时自动 POST。
 */

import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface VerifyEmailResponse {
  ok: boolean
  verified_at: string
}

async function verifyRequest(token: string): Promise<VerifyEmailResponse> {
  const { data } = await api.post<VerifyEmailResponse>('/me/verify-email', { token })
  return data
}

export function useVerifyEmail() {
  return useMutation({
    mutationFn: verifyRequest,
  })
}
