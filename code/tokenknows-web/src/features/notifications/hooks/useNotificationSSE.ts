/**
 * useNotificationSSE · v0.5.2 T54 实时通知订阅.
 *
 * 订阅 GET /api/v1/me/notifications/stream?user_id= (EventSource).
 * 服务端事件:
 *   - snapshot (订阅时一次, 携带当前 unread_count)
 *   - consent_request / consent_signed / consent_rejected / consent_expired
 *   - T129 · asset_chapter_rejected (作者侧, reviewer 退回章节实时推送)
 *
 * 行为:
 *   - 收到任意事件 → invalidate ['notifications', ...] queries
 *   - 收到 asset_chapter_rejected → 同时 invalidate todos / asset 详情 query
 *   - 浏览器原生 EventSource 不携带 Authorization 头, MVP 用 user_id query param
 *   - 自动重连 (浏览器原生); 不可恢复时会保留最后 known unread_count
 *
 * 与 useUnreadCount 的关系:
 *   - useUnreadCount 仍跑 60s polling 作为兜底 (proxy 掐 SSE 时)
 *   - 但绝大部分时间 SSE 会先于 polling 把 cache 标 stale
 */

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

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

export function useNotificationSSE({
  userId,
  enabled = true,
  onEvent,
}: UseNotificationSSEOptions): void {
  const qc = useQueryClient()
  const eventSourceRef = useRef<EventSource | null>(null)
  const onEventRef = useRef(onEvent)

  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    if (!enabled || !userId) return

    const url = `/api/v1/me/notifications/stream?user_id=${encodeURIComponent(
      userId,
    )}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    function handle(eventName: NotificationSSEEvent['event']) {
      return (e: MessageEvent): void => {
        let parsed: NotificationSSEEvent
        try {
          parsed = { ...JSON.parse(e.data), event: eventName }
        } catch {
          // 心跳或非 JSON: 忽略, 但仍触发 invalidate (兜底)
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

        // 同步 query cache: 任何事件都 invalidate notifications
        void qc.invalidateQueries({ queryKey: ['notifications'] })

        // consent_signed/rejected/expired 还可能影响 Skill 详情页
        if (parsed.skill_id && parsed.event !== 'snapshot') {
          void qc.invalidateQueries({
            queryKey: ['skills', 'detail', parsed.skill_id],
          })
          // 项目级列表也 invalidate (不知道 project_id, 全 invalidate)
          void qc.invalidateQueries({ queryKey: ['skills'] })
        }

        // T129 · 章节退回事件 → 同步刷新 todos + 当前 asset 详情 + chapters
        // 让工作台 TodoList / DocumentPage banner 即时更新
        if (parsed.event === 'asset_chapter_rejected') {
          // 不知道作者当前在看哪个 project, 全 todos query 都 invalidate
          // (queryKey 形如 ['projects', projectId, 'todos'])
          void qc.invalidateQueries({ queryKey: ['projects'] })
          if (parsed.asset_id) {
            void qc.invalidateQueries({ queryKey: ['assets', parsed.asset_id] })
            void qc.invalidateQueries({
              queryKey: ['assets', parsed.asset_id, 'chapters'],
            })
          }
        }
      }
    }

    es.addEventListener('snapshot', handle('snapshot'))
    es.addEventListener('consent_request', handle('consent_request'))
    es.addEventListener('consent_signed', handle('consent_signed'))
    es.addEventListener('consent_rejected', handle('consent_rejected'))
    es.addEventListener('consent_expired', handle('consent_expired'))
    es.addEventListener('asset_chapter_rejected', handle('asset_chapter_rejected'))

    es.onerror = () => {
      // 浏览器自动重连; 长断时 polling (useUnreadCount) 兜底
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [userId, enabled, qc])
}
