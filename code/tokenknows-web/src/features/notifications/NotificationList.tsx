/**
 * NotificationList · Popover 内的通知列表 (v0.5.1 T51).
 */

import type { WebNotification } from '@/types/api'
import { NotificationItem } from './NotificationItem'

interface NotificationListProps {
  notifications: WebNotification[]
  onNavigate?: () => void
  isLoading?: boolean
  error?: string | null
}

export function NotificationList({
  notifications,
  onNavigate,
  isLoading = false,
  error = null,
}: NotificationListProps) {
  if (isLoading) {
    return (
      <div className="p-6 text-center text-sm text-text-tertiary">
        加载中…
      </div>
    )
  }
  if (error) {
    return (
      <div
        className="p-4 text-center text-sm text-danger"
        data-testid="notification-list-error"
      >
        {error}
      </div>
    )
  }
  if (notifications.length === 0) {
    return (
      <div
        className="p-8 text-center text-sm text-text-tertiary"
        data-testid="notification-list-empty"
      >
        暂无通知 🌿
      </div>
    )
  }
  return (
    <div
      className="max-h-96 overflow-y-auto"
      data-testid="notification-list"
      role="list"
    >
      {notifications.map((n) => (
        <NotificationItem
          key={n.id}
          notification={n}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  )
}
