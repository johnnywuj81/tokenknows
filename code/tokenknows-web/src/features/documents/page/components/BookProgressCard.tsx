/**
 * BookProgressCard · v0.2 book 长文档生成进度
 *
 * 监听新 SSE 事件:
 *   - volume_outline_completed → 卷大纲完成
 *   - chapter_outline_completed → 单卷的章大纲完成 (payload.volume_index / chapter_count)
 *   - chapter_completed (stage=content) → 章正文完成
 *
 * 展示:
 *   "卷 2 / 5  ·  章 18 / 47  ·  预计剩余 ~6 分钟"
 *
 * 由 DocumentPage 在 asset.type === 'book' 且 status==='generating' 时挂载.
 */

import { useEffect, useReducer } from 'react'
import { Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { useGenerationSSE } from '../../hooks/useGenerationSSE'

interface BookProgressCardProps {
  assetId: string
  enabled: boolean
}

interface BookProgressState {
  volumesTotal: number       // volume_outline_completed.payload.volumes_total
  volumesCompleted: number   // chapter_outline_completed 累计计数
  chaptersTotal: number      // sum(chapter_outline_completed.chapter_count)
  chaptersCompleted: number  // chapter_completed (stage=content) 累计
  startedAt: number          // 用于估算剩余时间
}

type BookProgressAction =
  | { type: 'volume_outline'; volumesTotal: number }
  | { type: 'chapter_outline'; chapterCount: number }
  | { type: 'chapter_completed' }
  | { type: 'reset' }

function reducer(state: BookProgressState, action: BookProgressAction): BookProgressState {
  switch (action.type) {
    case 'volume_outline':
      return { ...state, volumesTotal: action.volumesTotal }
    case 'chapter_outline':
      return {
        ...state,
        volumesCompleted: state.volumesCompleted + 1,
        chaptersTotal: state.chaptersTotal + action.chapterCount,
      }
    case 'chapter_completed':
      return { ...state, chaptersCompleted: state.chaptersCompleted + 1 }
    case 'reset':
      return {
        volumesTotal: 0,
        volumesCompleted: 0,
        chaptersTotal: 0,
        chaptersCompleted: 0,
        startedAt: Date.now(),
      }
    default:
      return state
  }
}

const INITIAL: BookProgressState = {
  volumesTotal: 0,
  volumesCompleted: 0,
  chaptersTotal: 0,
  chaptersCompleted: 0,
  startedAt: 0,
}

function formatEta(state: BookProgressState): string {
  if (state.chaptersCompleted === 0 || state.chaptersTotal === 0) {
    return '—'
  }
  const elapsedMs = Date.now() - state.startedAt
  const perChapterMs = elapsedMs / state.chaptersCompleted
  const remaining = state.chaptersTotal - state.chaptersCompleted
  if (remaining <= 0) return '即将完成'
  const remainingMs = perChapterMs * remaining
  const min = Math.round(remainingMs / 60_000)
  if (min < 1) return '< 1 分钟'
  if (min > 60) return `~ ${Math.round(min / 60)} 小时`
  return `~ ${min} 分钟`
}

export function BookProgressCard({ assetId, enabled }: BookProgressCardProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL)

  // 启用时重置计时器
  useEffect(() => {
    if (enabled) dispatch({ type: 'reset' })
  }, [enabled, assetId])

  useGenerationSSE({
    assetId,
    enabled,
    onEvent: (event) => {
      const payload = (event.payload ?? {}) as Record<string, unknown>
      if (event.event === 'volume_outline_completed') {
        const volumesTotal = Number(payload.volumes_total) || 0
        dispatch({ type: 'volume_outline', volumesTotal })
      } else if (event.event === 'chapter_outline_completed') {
        const chapterCount = Number(payload.chapter_count) || 0
        dispatch({ type: 'chapter_outline', chapterCount })
      } else if (event.event === 'chapter_completed' && event.stage === 'content') {
        dispatch({ type: 'chapter_completed' })
      }
    },
  })

  if (!enabled) return null

  const volTotal = state.volumesTotal || state.volumesCompleted || '?'
  const chTotal = state.chaptersTotal || '?'

  return (
    <Card
      role="status"
      aria-live="polite"
      className="mx-6 my-4 flex items-center gap-3 border-l-4 border-l-accent-primary bg-accent-primary-light/40 px-4 py-3"
    >
      <Loader2 className="size-4 shrink-0 animate-spin text-accent-primary-dark" />
      <div className="flex flex-1 flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="font-ui text-body-sm font-medium text-text-primary">
          书籍生成中
        </span>
        <span className="font-mono text-body-sm text-text-secondary">
          卷 {state.volumesCompleted} / {volTotal}
          {' · '}
          章 {state.chaptersCompleted} / {chTotal}
        </span>
        <span className="font-ui text-xs text-text-tertiary">
          预计剩余 {formatEta(state)}
        </span>
      </div>
    </Card>
  )
}
