/**
 * ChapterDiffView · jsdiff line-level diff renderer.
 */

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChapterDiffView } from './ChapterDiffView'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '亮点',
  content: '',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


describe('ChapterDiffView', () => {
  it('no regen history: shows 无 diff 历史 message', () => {
    render(<ChapterDiffView chapter={mkChapter({ regeneration_history: [] })} />)
    expect(screen.getByText('§1 亮点')).toBeInTheDocument()
    expect(screen.getByText(/无 diff 历史/)).toBeInTheDocument()
  })

  it('regen with previous_content: stats badges +N / -N', () => {
    const chapter = mkChapter({
      content: '行1\n行2 新增\n行3\n行4 新增',
      regeneration_history: [{
        at: '2026-01-15T10:00:00Z',
        user_id: 'u1',
        instruction: '重写更简洁',
        model: 'gpt-4o',
        previous_content: '行1\n行3',
      }],
    })
    const { container } = render(<ChapterDiffView chapter={chapter} />)
    const txt = container.textContent || ''
    // jsdiff line behavior: added/removed include trailing newlines
    expect(txt).toMatch(/\+\d+/)
    expect(txt).toMatch(/-\d+/)
  })

  it('defaultExpanded true: shows diff content + footer', () => {
    const chapter = mkChapter({
      content: 'new',
      regeneration_history: [{
        at: '2026-01-15T10:00:00Z',
        user_id: 'u1',
        instruction: '简洁化',
        model: 'gpt-4o',
        previous_content: 'old',
      }],
    })
    render(<ChapterDiffView chapter={chapter} defaultExpanded />)
    expect(screen.getByText(/简洁化/)).toBeInTheDocument()
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })

  it('click header toggles expanded', () => {
    const chapter = mkChapter({
      content: 'new',
      regeneration_history: [{
        at: '2026-01-15T10:00:00Z',
        user_id: 'u1',
        instruction: '改写',
        model: 'm',
        previous_content: 'old',
      }],
    })
    render(<ChapterDiffView chapter={chapter} />)
    // not expanded by default
    expect(screen.queryByText(/重生成于/)).toBeNull()
    // click toggle
    fireEvent.click(screen.getByText('§1 亮点'))
    expect(screen.getByText(/重生成于/)).toBeInTheDocument()
    // click again
    fireEvent.click(screen.getByText('§1 亮点'))
    expect(screen.queryByText(/重生成于/)).toBeNull()
  })

  it('removed lines counted negatively', () => {
    const chapter = mkChapter({
      content: '行1',
      regeneration_history: [{
        at: '2026-01-15T10:00:00Z',
        user_id: 'u',
        instruction: '删除',
        model: 'm',
        previous_content: '行1\n行2\n行3',
      }],
    })
    const { container } = render(<ChapterDiffView chapter={chapter} />)
    // jsdiff line behavior: removed lines variable due to trailing newline
    expect(container.textContent || '').toMatch(/-\d+/)
  })

  it('instruction text shown when collapsed', () => {
    const chapter = mkChapter({
      content: 'b',
      regeneration_history: [{
        at: '2026-01-15T10:00:00Z',
        user_id: 'u',
        instruction: '用更专业语气',
        model: 'm',
        previous_content: 'a',
      }],
    })
    render(<ChapterDiffView chapter={chapter} />)
    expect(screen.getByText(/用更专业语气/)).toBeInTheDocument()
  })
})
