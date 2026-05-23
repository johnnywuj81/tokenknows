/**
 * NotificationBell · AppLayout 顶栏右侧铃铛 + 角标 (v0.5.1 T51).
 *
 * 行为:
 *   - 铃铛右上角红色角标 = unread_count
 *   - 点击展开 DropdownMenu, 内含 NotificationList
 *   - 顶部 "全部已读" 按钮 (有未读时)
 *   - 角标超过 99 显示 "99+"
 *
 * 未实现 (v0.5.2):
 *   - SSE 实时推送
 *   - 通知分组 (按 skill / 按类型)
 */

import { useState } from 'react'
import { Bell } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import {
  useMarkAllNotificationsRead,
  useNotifications,
  useUnreadCount,
} from './hooks/useNotifications'
import { useNotificationSSE } from './hooks/useNotificationSSE'
import { NotificationList } from './NotificationList'

export function NotificationBell() {
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const [open, setOpen] = useState(false)
  // SSE 主路径 (实时); 60s polling 兜底 (proxy 掐线时)
  useNotificationSSE({ userId, enabled: !!userId })
  const unreadQuery = useUnreadCount(60_000)
  const listQuery = useNotifications(false, 20)
  const markAllRead = useMarkAllNotificationsRead()

  const unread = unreadQuery.data ?? 0
  const notifications = listQuery.data ?? []
  const badge =
    unread === 0 ? null : unread > 99 ? '99+' : String(unread)

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="relative inline-flex items-center justify-center rounded-md p-2 text-text-secondary hover:bg-bg-hover hover:text-text-primary"
          aria-label={`通知 (${unread} 未读)`}
          data-testid="notification-bell"
        >
          <Bell className="size-5" />
          {badge && (
            <span
              className="absolute -right-0.5 -top-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-danger px-1 font-mono text-[10px] font-medium text-inverse-text"
              data-testid="notification-bell-badge"
            >
              {badge}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-96 p-0"
        data-testid="notification-popover"
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
          <p className="font-ui text-sm font-medium text-text-primary">
            通知 {unread > 0 && <span className="text-text-secondary">({unread} 未读)</span>}
          </p>
          {unread > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
              data-testid="notification-mark-all-read"
            >
              全部已读
            </Button>
          )}
        </div>

        <NotificationList
          notifications={notifications}
          isLoading={listQuery.isLoading}
          error={listQuery.error ? '加载通知失败' : null}
          onNavigate={() => setOpen(false)}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
