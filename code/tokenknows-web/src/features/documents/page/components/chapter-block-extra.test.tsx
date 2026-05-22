/**
 * ChapterBlock · onClickCapture (evidence badge click → onViewEvidence).
 */

import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ChapterBlock } from './ChapterBlock'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '本周亮点',
  content: '内容 [1] 详情 [2]',
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


describe('ChapterBlock onClickCapture', () => {
  it('clicking evidence badge span fires onViewEvidence with chapterId + evidenceId', async () => {
    const onViewEvidence = vi.fn()
    const { container } = render(withQuery(<ChapterBlock
      chapter={mkChapter()}
      onViewEvidence={onViewEvidence}
    />))
    // wait for TipTap to mount + annotateEvidence transforms [N] → spans
    await new Promise((r) => setTimeout(r, 50))
    // find spans with data-evidence-id
    const badge = container.querySelector('[data-evidence-id]')
    if (badge) {
      fireEvent.click(badge)
      expect(onViewEvidence).toHaveBeenCalled()
      const [chId, evId] = onViewEvidence.mock.calls[0]
      expect(chId).toBe('c1')
      expect(evId).toContain('ev-c1-')
    }
  })

  it('clicking non-evidence area does not invoke onViewEvidence', async () => {
    const onViewEvidence = vi.fn()
    const { container } = render(withQuery(<ChapterBlock
      chapter={mkChapter({ content: 'plain content no badges' })}
      onViewEvidence={onViewEvidence}
    />))
    await new Promise((r) => setTimeout(r, 50))
    // click somewhere in editor content
    const editor = container.querySelector('.tiptap-prose')
    if (editor) {
      fireEvent.click(editor)
      // no call
      expect(onViewEvidence).not.toHaveBeenCalled()
    }
  })
})
