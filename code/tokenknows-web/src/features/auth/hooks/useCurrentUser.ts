/**
 * useCurrentUser · GET /me 拉取当前用户信息。
 *
 * 用法: AppLayout / Workbench 等需要展示用户信息时使用。
 * 默认在已登录 (authStore.isAuthenticated) 时启用,避免触发 401 redirect 循环。
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types/api'

async function fetchCurrentUser(): Promise<User> {
  const { data } = await api.get<User>('/me')
  return data
}

export function useCurrentUser() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const setUser = useAuthStore((s) => s.setUser)

  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const user = await fetchCurrentUser()
      setUser(user)
      return user
    },
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,    // 5min - user info 很少变
  })
}
