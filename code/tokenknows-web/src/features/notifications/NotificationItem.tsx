/**
 * NotificationItem · 通知列表单项 (v0.5.1 T51).
 *
 * 4 种 type 用不同 emoji + 颜色;
 * 已读 / 未读视觉差异 (read=true 时整行降饱和度);
 * 点击 → mark_read + 跳 link_url.
 */

import { Link } from 'react-router-dom'
import type { WebNotification } from '@/types/api'
import { useMarkNotificationRead } from './hooks/useNotifications'

const TYPE_EMOJI: Record<WebNotification['type'], string> = {
  consent_request: '🤖',
  consent_signed: '✅',
  consent_rejected: '❌',
  consent_expired: '⏰',
  // v0.6.0 review
  skill_review_request: '📝',
  skill_review_approved: '✅',
  skill_review_rejected: '❌',
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}小时前`
  return `${Math.floor(hr / 24)}天前`
}

interface NotificationItemProps {
  notification: WebNotification
  onNavigate?: () => void
}

export function NotificationItem({
  notification,
  onNavigate,
}: NotificationItemProps) {
  const markRead = useMarkNotificationRead()

  const handleClick = (): void => {
    if (!notification.read) {
      markRead.mutate(notification.id)
    }
    onNavigate?.()
  }

  return (
    <Link
      to={notification.link_url}
      onClick={handleClick}
      className={`flex items-start gap-3 border-b border-border-subtle p-3 last:border-b-0 hover:bg-bg-hover ${
        notification.read ? 'opacity-60' : 'bg-bg-card'
      }`}
      data-testid={`notification-item-${notification.id}`}
      data-read={notification.read}
    >
      <span className="text-lg leading-none">
        {TYPE_EMOJI[notification.type]}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="font-ui text-sm font-medium text-text-primary line-clamp-1">
            {notification.title}
          </p>
          <span className="shrink-0 font-mono text-xs text-text-tertiary">
            {timeAgo(notification.created_at)}
          </span>
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-text-secondary">
          {notification.body}
        </p>
      </div>
      {!notification.read && (
        <span
          className="mt-1 size-2 shrink-0 rounded-full bg-accent-primary"
          aria-label="未读"
        />
      )}
    </Link>
  )
}
