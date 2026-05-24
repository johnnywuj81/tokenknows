/**
 * useNotificationSSE · v0.5.2 T54 实时通知订阅.
 *
 * 订阅 GET /api/v1/me/notifications/stream?user_id= (SSE).
 * 服务端事件:
 *   - snapshot (订阅时一次, 携带当前 unread_count)
 *   - consent_request / consent_signed / consent_rejected / consent_expired
 *   - T129 · asset_chapter_rejected (作者侧, reviewer 退回章节实时推送)
 *
 * 行为:
 *   - 收到任意事件 → invalidate ['notifications', ...] queries
 *   - 收到 asset_chapter_rejected → 同时 invalidate todos / asset 详情 query
 *   - 用 @microsoft/fetch-event-source 替代浏览器原生 EventSource,
 *     因原生 EventSource 不能带 Authorization header (T132 SSE auth 修复)
 *   - 自动重连; 不可恢复时会保留最后 known unread_count
 *
 * 与 useUnreadCount 的关系:
 *   - useUnreadCount 仍跑 60s polling 作为兜底 (proxy 掐 SSE 时)
 *   - 但绝大部分时间 SSE 会先于 polling 把 cache 标 stale
 */

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { fetchEventSource, type EventSourceMessage } from '@microsoft/fetch-event-source'
import { useAuthStore } from '@/stores/authStore'

interface NotificationSSEEvent {
  event:
    | 'snapshot'
    | 'consent_request'
    | 'consent_signed'
    | 'consent_rejected'
    | 'consent_expired'
    | 'asset_chapter_rejected'  // T129
  user_id: string
  skill_id: string | null
  asset_id: string | null       // T129 · asset_chapter_rejected 用
  notification_id: string | null
  unread_count: number | null
  extra: Record<string, unknown>
  timestamp: string
}

interface UseNotificationSSEOptions {
  /** 当前登录用户 id; null 时不订阅. */
  userId: string | null | undefined
  /** 默认 true; 关闭可用 polling 兜底. */
  enabled?: boolean
  onEvent?: (event: NotificationSSEEvent) => void
}

const KNOWN_EVENTS: NotificationSSEEvent['event'][] = [
  'snapshot',
  'consent_request',
  'consent_signed',
  'consent_rejected',
  'consent_expired',
  'asset_chapter_rejected',
]

class FatalAuthError extends Error {}

export function useNotificationSSE({
  userId,
  enabled = true,
  onEvent,
}: UseNotificationSSEOptions): void {
  const qc = useQueryClient()
  const onEventRef = useRef(onEvent)

  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    if (!enabled || !userId) return

    const controller = new AbortController()
    const url = `/api/v1/me/notifications/stream?user_id=${encodeURIComponent(userId)}`

    function dispatch(ev: EventSourceMessage): void {
      const eventName = ev.event as NotificationSSEEvent['event']
      if (!KNOWN_EVENTS.includes(eventName)) return  // 跳过 heartbeat / 未知

      let parsed: NotificationSSEEvent
      try {
        parsed = { ...JSON.parse(ev.data), event: eventName }
      } catch {
        parsed = {
          event: eventName,
          user_id: userId,
          skill_id: null,
          asset_id: null,
          notification_id: null,
          unread_count: null,
          extra: {},
          timestamp: new Date().toISOString(),
        }
      }
      onEventRef.current?.(parsed)

      void qc.invalidateQueries({ queryKey: ['notifications'] })

      if (parsed.skill_id && parsed.event !== 'snapshot') {
        void qc.invalidateQueries({ queryKey: ['skills', 'detail', parsed.skill_id] })
        void qc.invalidateQueries({ queryKey: ['skills'] })
      }

      // T129 · 章节退回事件 → 同步刷新 todos + 当前 asset 详情 + chapters
      if (parsed.event === 'asset_chapter_rejected') {
        void qc.invalidateQueries({ queryKey: ['projects'] })
        if (parsed.asset_id) {
          void qc.invalidateQueries({ queryKey: ['assets', parsed.asset_id] })
          void qc.invalidateQueries({
            queryKey: ['assets', parsed.asset_id, 'chapters'],
          })
        }
      }
    }

    // 与 axios interceptor 同样的 header 注入逻辑 (lib/api.ts)
    function buildAuthHeaders(): Record<string, string> {
      const state = useAuthStore.getState()
      const headers: Record<string, string> = {
        Accept: 'text/event-stream',
      }
      if (state.accessToken) {
        headers.Authorization = `Bearer ${state.accessToken}`
      }
      if (state.user?.id) {
        headers['X-User-Id'] = state.user.id
      }
      return headers
    }

    void fetchEventSource(url, {
      signal: controller.signal,
      headers: buildAuthHeaders(),
      // 防止页面退入后台时主动关闭 (内置默认行为太激进)
      openWhenHidden: true,
      onopen: async (response) => {
        if (response.ok && response.headers.get('content-type')?.startsWith('text/event-stream')) {
          return
        }
        // 401/403 → 致命, 不重连; 其它 (5xx / 网络) 让 onerror 处理重连
        if (response.status === 401 || response.status === 403) {
          throw new FatalAuthError(`SSE auth failed: ${response.status}`)
        }
        throw new Error(`SSE open failed: ${response.status}`)
      },
      onmessage: dispatch,
      onerror: (err) => {
        if (err instanceof FatalAuthError) {
          throw err  // 抛出去停止重连
        }
        // 其它错误: return undefined 让 fetch-event-source 退避重试 (默认 1s)
        return undefined
      },
    }).catch((err) => {
      if (err instanceof FatalAuthError) {
        // polling (useUnreadCount) 会兜底, 这里只 debug log
        // eslint-disable-next-line no-console
        console.warn('[notification SSE] disabled due to auth failure; falling back to polling.', err.message)
      }
      // 其它非 fatal 错误已被库重连吞掉, 这里不到
    })

    return () => {
      controller.abort()
    }
  }, [userId, enabled, qc])
}
