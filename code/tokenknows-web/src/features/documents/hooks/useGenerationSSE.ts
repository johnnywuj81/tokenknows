/**
 * useGenerationSSE · P4 文档生成 SSE 订阅
 *
 * 订阅 GET /api/v1/assets/:id/generation/stream (EventSource).
 * 服务端事件: snapshot / stage_started / stage_completed / chapter_completed
 *           / done / failed
 *           / volume_outline_completed / chapter_outline_completed (v0.2 book)
 *
 * onEvent: 触发 TanStack Query invalidate 让 useAsset/useChapters 拉新.
 *
 * 仅当 assetId 存在 + status 为 generating/in_progress 时订阅, 完成后自动关闭.
 *
 * 注意: 浏览器原生 EventSource 不携带 cookie 跨 origin, 不传 Authorization
 * 头. 这里走 Vite proxy (同 origin) + MVP 不需要鉴权, 后续生产换 WebSocket
 * 或 fetch-stream 替代.
 */

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface SSEEvent {
  event: string
  asset_id?: string
  stage?: string
  payload?: Record<string, unknown>
  ts?: string
}

interface UseGenerationSSEOptions {
  assetId: string | null | undefined
  /** 是否启用订阅 (通常 status === 'generating' 时开). */
  enabled: boolean
  onEvent?: (event: SSEEvent) => void
}

export function useGenerationSSE({
  assetId,
  enabled,
  onEvent,
}: UseGenerationSSEOptions) {
  const qc = useQueryClient()
  const eventSourceRef = useRef<EventSource | null>(null)
  const onEventRef = useRef(onEvent)

  // 同步 callback ref (避免重新订阅)
  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    if (!enabled || !assetId) return

    const url = `/api/v1/assets/${assetId}/generation/stream`
    const es = new EventSource(url)
    eventSourceRef.current = es

    function handle(eventName: string) {
      return (e: MessageEvent) => {
        let parsed: SSEEvent = { event: eventName }
        try {
          parsed = { ...JSON.parse(e.data), event: eventName }
        } catch {
          // 心跳或非 JSON 事件
        }
        onEventRef.current?.(parsed)

        // TanStack Query 同步:
        if (eventName === 'snapshot' || eventName === 'stage_started' || eventName === 'stage_completed') {
          // progress 自带在事件 payload 里 - 但 useProgress 仍可能存在 cache, invalidate 它
          void qc.invalidateQueries({ queryKey: ['assets', assetId, 'progress'] })
        }
        if (eventName === 'chapter_completed') {
          void qc.invalidateQueries({ queryKey: ['assets', assetId, 'chapters'] })
        }
        if (eventName === 'done') {
          void qc.invalidateQueries({ queryKey: ['assets', assetId] })
          void qc.invalidateQueries({ queryKey: ['assets', assetId, 'chapters'] })
          // 文档完成后自然关闭 SSE
          es.close()
        }
        if (eventName === 'failed') {
          void qc.invalidateQueries({ queryKey: ['assets', assetId] })
          es.close()
        }
      }
    }

    // 后端按事件类型发, 必须分别注册 listener
    es.addEventListener('snapshot', handle('snapshot'))
    es.addEventListener('stage_started', handle('stage_started'))
    es.addEventListener('stage_completed', handle('stage_completed'))
    es.addEventListener('chapter_completed', handle('chapter_completed'))
    es.addEventListener('done', handle('done'))
    es.addEventListener('failed', handle('failed'))
    // v0.2 · book 两步大纲进度
    es.addEventListener('volume_outline_completed', handle('volume_outline_completed'))
    es.addEventListener('chapter_outline_completed', handle('chapter_outline_completed'))

    es.onerror = () => {
      // 浏览器会自动重连 - 仅日志
      // (生产环境留意: 长时间断连可能要切轮询兜底)
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [assetId, enabled, qc])
}
