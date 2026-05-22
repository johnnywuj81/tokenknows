/**
 * ChapterBlock · SaveBadge 各状态分支 (idle / editing / saving / saved / error).
 *
 * 通过 mock useChapterAutosave hook 注入各种状态 → 验证 SaveBadge 渲染.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { Chapter } from '@/types/api'


// Hoisted mock - vi.mock factory must not capture outer scope
const stateRef = { state: 'idle', error: null as string | null }


vi.mock('@/features/documents/hooks/useChapterAutosave', () => ({
  useChapterAutosave: (chapter: Chapter) => ({
    state: stateRef.state,
    savedContent: chapter.content,
    handleEdit: () => {},
    error: stateRef.error,
  }),
}))


// Must import after mock declaration
const { ChapterBlock } = await import('./ChapterBlock')


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


const mkChapter = (): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: 'T', content: '内容', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
})


describe('ChapterBlock SaveBadge states', () => {
  beforeEach(() => {
    stateRef.state = 'idle'
    stateRef.error = null
  })

  it('idle: no SaveBadge text rendered', () => {
    stateRef.state = 'idle'
    render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.queryByText('编辑中…')).toBeNull()
    expect(screen.queryByText('保存中')).toBeNull()
    expect(screen.queryByText('已保存')).toBeNull()
  })

  it('editing: 编辑中… text rendered', () => {
    stateRef.state = 'editing'
    render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.getByText('编辑中…')).toBeInTheDocument()
  })

  it('saving: 保存中 + spinner rendered', () => {
    stateRef.state = 'saving'
    render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.getByText('保存中')).toBeInTheDocument()
  })

  it('saved: 已保存 + checkmark', () => {
    stateRef.state = 'saved'
    render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.getByText('已保存')).toBeInTheDocument()
  })

  it('error: 已存本地 (重试中) + title attribute = error msg', () => {
    stateRef.state = 'error'
    stateRef.error = '网络异常'
    const { container } = render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.getByText(/已存本地/)).toBeInTheDocument()
    const errSpan = container.querySelector('[title="网络异常"]')
    expect(errSpan).not.toBeNull()
  })

  it('error with null msg: title = 保存失败 fallback', () => {
    stateRef.state = 'error'
    stateRef.error = null
    const { container } = render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(container.querySelector('[title="保存失败"]')).not.toBeNull()
  })
})
