/**
 * BookProgressCard · v0.2 book 进度卡
 *
 * 覆盖:
 * - enabled=false 时不渲染
 * - 收到 volume_outline_completed → 卷总数显示
 * - 收到 chapter_outline_completed → 卷完成 + 章总数累加
 * - 收到 chapter_completed (stage=content) → 章完成累加
 * - ETA 在有完成章节后展示分钟数
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// 在 import 组件前 mock useGenerationSSE
let lastOnEvent: ((event: { event: string; stage?: string; payload?: Record<string, unknown> }) => void) | null = null
vi.mock('../../hooks/useGenerationSSE', () => ({
  useGenerationSSE: ({
    onEvent,
  }: {
    assetId: string
    enabled: boolean
    onEvent?: (e: { event: string; stage?: string; payload?: Record<string, unknown> }) => void
  }) => {
    lastOnEvent = onEvent ?? null
  },
}))

import { BookProgressCard } from './BookProgressCard'


function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('BookProgressCard', () => {
  beforeEach(() => {
    lastOnEvent = null
  })

  it('renders nothing when disabled', () => {
    const { container } = wrap(<BookProgressCard assetId="a1" enabled={false} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders initial state with placeholders', () => {
    wrap(<BookProgressCard assetId="a1" enabled />)
    expect(screen.getByText('书籍生成中')).toBeInTheDocument()
    // 初始: 0 / ? · 0 / ?
    expect(screen.getByText(/卷 0 \/ \?/)).toBeInTheDocument()
    expect(screen.getByText(/章 0 \/ \?/)).toBeInTheDocument()
  })

  it('updates volume total on volume_outline_completed', () => {
    wrap(<BookProgressCard assetId="a1" enabled />)
    act(() => {
      lastOnEvent?.({
        event: 'volume_outline_completed',
        payload: { volumes_total: 3 },
      })
    })
    expect(screen.getByText(/卷 0 \/ 3/)).toBeInTheDocument()
  })

  it('increments volumes_completed + chapters_total on chapter_outline_completed', () => {
    wrap(<BookProgressCard assetId="a1" enabled />)
    act(() => {
      lastOnEvent?.({
        event: 'volume_outline_completed',
        payload: { volumes_total: 2 },
      })
      lastOnEvent?.({
        event: 'chapter_outline_completed',
        payload: { volume_index: 0, chapter_count: 5 },
      })
      lastOnEvent?.({
        event: 'chapter_outline_completed',
        payload: { volume_index: 1, chapter_count: 7 },
      })
    })
    expect(screen.getByText(/卷 2 \/ 2/)).toBeInTheDocument()
    expect(screen.getByText(/章 0 \/ 12/)).toBeInTheDocument()
  })

  it('increments chapters_completed only when stage=content', () => {
    wrap(<BookProgressCard assetId="a1" enabled />)
    act(() => {
      lastOnEvent?.({
        event: 'chapter_outline_completed',
        payload: { chapter_count: 4 },
      })
      lastOnEvent?.({
        event: 'chapter_completed',
        stage: 'content',
      })
      lastOnEvent?.({
        event: 'chapter_completed',
        stage: 'content',
      })
      // outline stage 的 chapter_completed 不算
      lastOnEvent?.({
        event: 'chapter_completed',
        stage: 'outline',
      })
    })
    expect(screen.getByText(/章 2 \/ 4/)).toBeInTheDocument()
  })

  it('shows ETA placeholder when 0 chapters done', () => {
    wrap(<BookProgressCard assetId="a1" enabled />)
    expect(screen.getByText(/预计剩余 —/)).toBeInTheDocument()
  })
})
