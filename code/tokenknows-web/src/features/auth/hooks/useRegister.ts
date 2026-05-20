/**
 * useRegister · 注册 mutation。
 *
 * 注意 (TaskTechDesign T01 关键决策):
 *   注册成功不自动登录,跳"请检查邮箱"中间页。
 *   故 onSuccess 不写 authStore,由 RegisterPage 切换本地 step。
 */

import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RegisterRequest, User } from '@/types/api'

interface RegisterResponse {
  user: User
  requires_verification: boolean
}

async function registerRequest(payload: RegisterRequest): Promise<RegisterResponse> {
  const { data } = await api.post<RegisterResponse>('/auth/register', payload)
  return data
}

export function useRegister() {
  return useMutation({
    mutationFn: registerRequest,
  })
}
