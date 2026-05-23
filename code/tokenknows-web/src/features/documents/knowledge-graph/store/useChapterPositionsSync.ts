/**
 * useChapterPositionsSync · v1.3 T91 · 节点拖动 → debounced PATCH 后端.
 *
 * 设计:
 *   - sync(positions) 入参为整套位置 snapshot, 调用方 (GraphCanvas) 在 onNodeDragStop
 *     之后从 positionStore 拿当前 snapshot 一并 PATCH
 *   - 500ms debounce, 拖快了不会刷爆后端
 *   - PATCH 替换语义 (full replace) — 与后端 generation_service.update_chapter_positions 对齐
 *   - 失败仅 console.warn, 不阻断 UI (本地 store 仍持久化, 用户感知不到失败)
 */

import { useCallback, useEffect, useRef } from 'react'
import { api, isApiError } from '@/lib/api'
import type { Chapter } from '@/types/api'

interface NodePosition {
  x: number
  y: number
}

interface UseChapterPositionsSyncResult {
  /** GraphCanvas 在 onNodeDragStop 后调用. */
  sync: (positions: Record<string, NodePosition>) => void
}

export function useChapterPositionsSync(
  assetId: string | null | undefined,
  chapterId: string | null | undefined,
): UseChapterPositionsSyncResult {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestRef = useRef<Record<string, NodePosition>>({})

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    },
    [],
  )

  const sync = useCallback(
    (positions: Record<string, NodePosition>) => {
      if (!assetId || !chapterId) return
      latestRef.current = positions
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(async () => {
        try {
          await api.patch<Chapter>(
            `/assets/${assetId}/chapters/${chapterId}/positions`,
            { positions: latestRef.current },
          )
        } catch (err: unknown) {
          const msg = isApiError(err) ? err.message : 'patch positions failed'
          // 非致命 · 本地 store 仍有最新位置
          console.warn('[T91] chapter positions sync failed:', msg)
        }
      }, 500)
    },
    [assetId, chapterId],
  )

  return { sync }
}
