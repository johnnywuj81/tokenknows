/**
 * ReviewTimeline · v0.8 T63 unit tests.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReviewRecord } from '@/types/api'
import { ReviewTimeline } from './ReviewTimeline'

describe('ReviewTimeline', () => {
  it('空 history 不渲染', () => {
    const { container } = render(<ReviewTimeline history={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('单条 submit 显示', () => {
    const records: ReviewRecord[] = [
      {
        reviewer_id: 'ou-alice',
        action: 'submit',
        timestamp: '2026-06-01T10:00:00Z',
        note: null,
      },
    ]
    render(<ReviewTimeline history={records} />)
    expect(screen.getByTestId('review-timeline')).toBeInTheDocument()
    expect(screen.getByText('提交审批')).toBeInTheDocument()
    expect(screen.getByText('by ou-alice')).toBeInTheDocument()
  })

  it('完整 cycle submit → reject → submit → approve', () => {
    const records: ReviewRecord[] = [
      {
        reviewer_id: 'ou-author',
        action: 'submit',
        timestamp: '2026-06-01T10:00:00Z',
        note: null,
      },
      {
        reviewer_id: 'ou-bob',
        action: 'reject',
        timestamp: '2026-06-02T10:00:00Z',
        note: '需要更多例子',
      },
      {
        reviewer_id: 'ou-author',
        action: 'submit',
        timestamp: '2026-06-03T10:00:00Z',
        note: '已添加',
      },
      {
        reviewer_id: 'ou-bob',
        action: 'approve',
        timestamp: '2026-06-04T10:00:00Z',
        note: 'LGTM',
      },
    ]
    render(<ReviewTimeline history={records} />)
    // 4 个 record 渲染
    expect(screen.getByTestId('review-record-0')).toBeInTheDocument()
    expect(screen.getByTestId('review-record-3')).toBeInTheDocument()
    // ✅ 批准 / ❌ 退回 显示
    expect(screen.getByText('✅ 批准')).toBeInTheDocument()
    expect(screen.getByText('❌ 退回')).toBeInTheDocument()
    // submit 2 次
    expect(screen.getAllByText('提交审批').length).toBe(2)
    // reject note 显示
    expect(screen.getByText('需要更多例子')).toBeInTheDocument()
  })

  it('reject 用 danger 色', () => {
    const records: ReviewRecord[] = [
      {
        reviewer_id: 'ou-bob',
        action: 'reject',
        timestamp: '2026-06-01',
        note: 'no',
      },
    ]
    render(<ReviewTimeline history={records} />)
    const label = screen.getByText('❌ 退回')
    expect(label.className).toContain('text-danger')
  })

  it('approve 用 success-dark 色', () => {
    const records: ReviewRecord[] = [
      {
        reviewer_id: 'ou-bob',
        action: 'approve',
        timestamp: '2026-06-01',
        note: null,
      },
    ]
    render(<ReviewTimeline history={records} />)
    const label = screen.getByText('✅ 批准')
    expect(label.className).toContain('text-success-dark')
  })
})
