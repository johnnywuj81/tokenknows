/**
 * useNotifications · TanStack Query hooks for v0.5.1 站内通知 (T49+T51).
 *
 * 后端端点:
 *   GET  /me/notifications?limit=50&unread_only=true
 *   GET  /me/notifications/unread-count
 *   POST /me/notifications/:id/read
 *   POST /me/notifications/read-all
 *
 * SSE 订阅 (T50): auto_trigger.consent_{request|signed|rejected|expired}
 * 当 SSE 不可用 (proxy / 防火墙) → polling unread-count 30s 兜底.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type {
  WebNotification,
  WebNotificationListResponse,
} from '@/types/api'

const notificationKey = {
  unreadCount: (userId: string | null) =>
    ['notifications', 'unread-count', userId ?? 'anon'] as const,
  list: (userId: string | null, unreadOnly?: boolean) =>
    ['notifications', 'list', userId ?? 'anon', unreadOnly ?? false] as const,
}

export function useUnreadCount(pollIntervalMs = 60_000) {
  const userId = useAuthStore((s) => s.user?.id ?? null)
  return useQuery({
    queryKey: notificationKey.unreadCount(userId),
    queryFn: async (): Promise<number> => {
      // v1.0.1 review fix: 替换 ! 非空断言为显式 guard
      if (!userId) throw new Error('userId required')
      const res = await api.get<{ unread_count: number }>(
        `/me/notifications/unread-count?user_id=${encodeURIComponent(userId)}`,
      )
      return res.data.unread_count
    },
    enabled: !!userId,
    refetchInterval: pollIntervalMs,
    refetchIntervalInBackground: false,
  })
}

export function useNotifications(unreadOnly = false, limit = 50) {
  const userId = useAuthStore((s) => s.user?.id ?? null)
  return useQuery({
    queryKey: notificationKey.list(userId, unreadOnly),
    queryFn: async (): Promise<WebNotification[]> => {
      // v1.0.1 review fix: 同上 guard
      if (!userId) throw new Error('userId required')
      const params = new URLSearchParams()
      params.set('user_id', userId)
      params.set('limit', String(limit))
      if (unreadOnly) params.set('unread_only', 'true')
      const res = await api.get<WebNotificationListResponse>(
        `/me/notifications?${params.toString()}`,
      )
      return res.data.items
    },
    enabled: !!userId,
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (notificationId: string) => {
      await api.post(`/me/notifications/${notificationId}/read`, {})
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  return useMutation({
    mutationFn: async () => {
      if (!userId) return
      await api.post(
        `/me/notifications/read-all?user_id=${encodeURIComponent(userId)}`,
        {},
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}
