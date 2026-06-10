/**
 * ChapterBlock onClickCapture · [N] 角标点击 → onViewEvidence(chapterId, evidenceId).
 *
 * 这条路径覆盖 ChapterBlock 内部的事件委托 + DocumentPage / ReviewPage
 * handleViewEvidence callback.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { Chapter } from '@/types/api'


// Hoisted mock - inject stable autosave state so editor mounts cleanly
const stateRef = { state: 'idle', error: null as string | null }


vi.mock('@/features/documents/hooks/useChapterAutosave', () => ({
  useChapterAutosave: (chapter: Chapter) => ({
    state: stateRef.state,
    savedContent: chapter.content,
    handleEdit: () => {},
    error: stateRef.error,
  }),
}))


const { ChapterBlock } = await import('./ChapterBlock')


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


const mkChapter = (): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: 'T', content: '段落 [1] 内容', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  redacted_spans: [],
  created_at: '', updated_at: '',
})


describe('ChapterBlock evidence badge click', () => {
  beforeEach(() => {
    stateRef.state = 'idle'
    stateRef.error = null
  })

  it('clicking [data-evidence-id] span fires onViewEvidence', () => {
    const onViewEvidence = vi.fn()
    const { container } = render(withQuery(<ChapterBlock
      chapter={mkChapter()}
      onViewEvidence={onViewEvidence}
    />))
    const badge = container.querySelector('[data-evidence-id]') as HTMLElement | null
    expect(badge).not.toBeNull()
    fireEvent.click(badge!)
    expect(onViewEvidence).toHaveBeenCalled()
    expect(onViewEvidence.mock.calls[0][0]).toBe('c1')
  })

  it('clicking child of badge: closest still finds parent', () => {
    const onViewEvidence = vi.fn()
    const { container } = render(withQuery(<ChapterBlock
      chapter={mkChapter()}
      onViewEvidence={onViewEvidence}
    />))
    const badge = container.querySelector('[data-evidence-id]') as HTMLElement
    // 即使点 badge 文本节点, closest 仍能找到
    fireEvent.click(badge.firstChild as Element ?? badge)
    expect(onViewEvidence).toHaveBeenCalled()
  })

  it('clicking outside badge: onViewEvidence not called', () => {
    const onViewEvidence = vi.fn()
    const { container } = render(withQuery(<ChapterBlock
      chapter={mkChapter()}
      onViewEvidence={onViewEvidence}
    />))
    // 点击 header (chapter title)
    const title = container.querySelector('h2')
    fireEvent.click(title!)
    expect(onViewEvidence).not.toHaveBeenCalled()
  })

  it('no onViewEvidence handler: click does not throw', () => {
    const { container } = render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    const badge = container.querySelector('[data-evidence-id]') as HTMLElement
    expect(() => fireEvent.click(badge)).not.toThrow()
  })
})
