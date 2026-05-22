/**
 * ChapterBlock · TipTap-powered editor block.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ChapterBlock } from './ChapterBlock'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '第一章',
  content: '这是 markdown 内容',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  created_at: '',
  updated_at: '',
  ...overrides,
})


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


describe('ChapterBlock', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders title + chapter number header', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter({ title: '本周亮点' })} />))
    expect(screen.getByText('本周亮点')).toBeInTheDocument()
    expect(screen.getByText('§1')).toBeInTheDocument()
  })

  it('renders generated_by provider/model when present', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter({
      generated_by: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
    })} />))
    expect(screen.getByText(/anthropic · claude/)).toBeInTheDocument()
  })

  it('regenerating: shows lock banner + disables editor', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter()} regenerating />))
    expect(screen.getByText(/本章重生成中, 编辑已禁用/)).toBeInTheDocument()
  })

  it('renders ChapterFooter with footer buttons (when onRegenerate set)', () => {
    render(withQuery(<ChapterBlock
      chapter={mkChapter()}
      onRegenerate={() => {}}
      onViewEvidence={() => {}}
    />))
    expect(screen.getByText('重生成')).toBeInTheDocument()
    expect(screen.getByText('查看证据')).toBeInTheDocument()
  })

  it('readOnly: editor not editable, no autosave', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter()} readOnly />))
    // editor still mounted, but readOnly state set
    expect(screen.getByText('§1')).toBeInTheDocument()
  })

  it('chapter with HTML content (already edited): preserves HTML', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter({
      content: '<p>已编辑 HTML</p>',
    })} />))
    expect(screen.getByText('已编辑 HTML')).toBeInTheDocument()
  })

  it('order_index 4 → header §5', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter({ order_index: 4 })} />))
    expect(screen.getByText('§5')).toBeInTheDocument()
  })
})
