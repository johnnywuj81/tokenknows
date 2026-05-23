/**
 * T128 · ChapterBlock RejectReasonBanner 显示退回理由.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ChapterBlock } from './ChapterBlock'
import type { Chapter } from '@/types/api'


const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 3,
  title: '风险与阻塞',
  content: '本周风险',
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


describe('ChapterBlock · RejectReasonBanner (T128)', () => {
  it('no banner when chapter not rejected', () => {
    render(withQuery(<ChapterBlock chapter={mkChapter()} />))
    expect(screen.queryByTestId('chapter-reject-banner-c1')).not.toBeInTheDocument()
  })

  it('renders reason from regeneration_history when approval_state=rejected', () => {
    render(
      withQuery(
        <ChapterBlock
          chapter={mkChapter({
            approval_state: 'rejected',
            regeneration_history: [
              {
                at: '2026-05-23T17:00:00Z',
                user_id: 'reviewer',
                instruction: '[REJECT] 风险评估不够具体, 缺少缓解措施',
                model: 'human',
              },
            ],
          })}
        />,
      ),
    )
    const banner = screen.getByTestId('chapter-reject-banner-c1')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveTextContent('审批人退回了本章')
    expect(banner).toHaveTextContent('风险评估不够具体, 缺少缓解措施')
  })

  it('shows placeholder when rejected but no [REJECT] entry in history', () => {
    render(
      withQuery(
        <ChapterBlock
          chapter={mkChapter({
            approval_state: 'rejected',
            regeneration_history: [
              // 只有 regenerate, 没有 REJECT (历史数据 / 异常)
              {
                at: '2026-05-23T16:00:00Z',
                user_id: 'author',
                instruction: '请改简洁',
                model: 'claude',
              },
            ],
          })}
        />,
      ),
    )
    const banner = screen.getByTestId('chapter-reject-banner-c1')
    expect(banner).toHaveTextContent('(未填理由)')
  })

  it('picks the LATEST [REJECT] when history has multiple', () => {
    render(
      withQuery(
        <ChapterBlock
          chapter={mkChapter({
            approval_state: 'rejected',
            regeneration_history: [
              {
                at: '2026-05-20T10:00:00Z',
                user_id: 'reviewer',
                instruction: '[REJECT] 第一次退回 (旧)',
                model: 'human',
              },
              {
                at: '2026-05-22T10:00:00Z',
                user_id: 'author',
                instruction: '我已修订',  // 不是 REJECT
                model: 'claude',
              },
              {
                at: '2026-05-23T17:00:00Z',
                user_id: 'reviewer',
                instruction: '[REJECT] 第二次退回 (新)',
                model: 'human',
              },
            ],
          })}
        />,
      ),
    )
    const banner = screen.getByTestId('chapter-reject-banner-c1')
    expect(banner).toHaveTextContent('第二次退回 (新)')
    expect(banner).not.toHaveTextContent('第一次退回 (旧)')
  })
})
