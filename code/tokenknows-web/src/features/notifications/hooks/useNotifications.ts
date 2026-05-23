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
import type {
  WebNotification,
  WebNotificationListResponse,
} from '@/types/api'

const notificationKey = {
  unreadCount: () => ['notifications', 'unread-count'] as const,
  list: (unreadOnly?: boolean) =>
    ['notifications', 'list', unreadOnly ?? false] as const,
}

export function useUnreadCount(pollIntervalMs = 30_000) {
  return useQuery({
    queryKey: notificationKey.unreadCount(),
    queryFn: async (): Promise<number> => {
      const res = await api.get<{ unread_count: number }>(
        '/me/notifications/unread-count',
      )
      return res.data.unread_count
    },
    // SSE 不可用时, 用 polling 兜底
    refetchInterval: pollIntervalMs,
    refetchIntervalInBackground: false,
  })
}

export function useNotifications(unreadOnly = false, limit = 50) {
  return useQuery({
    queryKey: notificationKey.list(unreadOnly),
    queryFn: async (): Promise<WebNotification[]> => {
      const params = new URLSearchParams()
      params.set('limit', String(limit))
      if (unreadOnly) params.set('unread_only', 'true')
      const res = await api.get<WebNotificationListResponse>(
        `/me/notifications?${params.toString()}`,
      )
      return res.data.items
    },
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
  return useMutation({
    mutationFn: async () => {
      await api.post('/me/notifications/read-all', {})
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}
