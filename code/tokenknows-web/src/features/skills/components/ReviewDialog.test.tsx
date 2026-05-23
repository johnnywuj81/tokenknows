/**
 * ReviewDialog · v0.6.0 T58 unit tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import type { Skill } from '@/types/api'
import { ReviewDialog } from './ReviewDialog'

const mock = new MockAdapter(api)

function _baseSkill(): Skill {
  const now = new Date().toISOString()
  return {
    id: 'skill-rv-1',
    project_id: 'proj-X',
    name: 'demo-rv',
    version: 1,
    skill_md: '---\n---\n',
    embedding: null,
    metrics: {
      usage_count: 0,
      acceptance_count: 0,
      rejection_count: 0,
      avg_acceptance_rate: 0,
      trust_score: 0.5,
    },
    distilled_from: [],
    distilled_at: now,
    last_used_at: null,
    locked: false,
    status: 'draft',
    parent_skill_id: null,
    contributors: ['ou-alice'],
    consent_required_from: [],
    consent_signed_by: [],
    consent_rejected_by: null,
    consent_expires_at: null,
    review_state: 'pending_review',
    review_history: [],
    last_reviewer_id: null,
    last_reviewed_at: null,
    created_at: now,
    updated_at: now,
  }
}

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mock.reset()
})

describe('ReviewDialog', () => {
  it('submit 模式: confirm 调 submit-for-review', async () => {
    mock.onPost('/skills/skill-rv-1/submit-for-review').reply(200, {
      skill_id: 'skill-rv-1',
      status: 'draft',
      review_state: 'pending_review',
      last_action: 'submit',
      last_reviewer_id: null,
      last_reviewed_at: null,
    })
    const onClose = vi.fn()
    _render(
      <ReviewDialog
        skill={_baseSkill()}
        action="submit"
        userId="ou-alice"
        onClose={onClose}
      />,
    )
    // 标题里含 "提交审批"
    expect(screen.getAllByText(/提交审批/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByTestId('review-dialog-confirm'))
    await new Promise((r) => setTimeout(r, 50))
    expect(onClose).toHaveBeenCalled()
    expect(mock.history.post.length).toBe(1)
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.user_id).toBe('ou-alice')
  })

  it('approve 模式: body 用 reviewer_id', async () => {
    mock.onPost('/skills/skill-rv-1/review/approve').reply(200, {
      skill_id: 'skill-rv-1',
      status: 'active',
      review_state: 'approved',
      last_action: 'approve',
      last_reviewer_id: 'ou-bob',
      last_reviewed_at: '',
    })
    const onClose = vi.fn()
    _render(
      <ReviewDialog
        skill={_baseSkill()}
        action="approve"
        userId="ou-bob"
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByTestId('review-dialog-confirm'))
    await new Promise((r) => setTimeout(r, 50))
    expect(onClose).toHaveBeenCalled()
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.reviewer_id).toBe('ou-bob')
  })

  it('reject 模式 reason < 5 → confirm disabled', () => {
    _render(
      <ReviewDialog
        skill={_baseSkill()}
        action="reject"
        userId="ou-bob"
        onClose={vi.fn()}
      />,
    )
    const confirm = screen.getByTestId('review-dialog-confirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByTestId('review-reject-reason-input'), {
      target: { value: 'no' },
    })
    expect(confirm.disabled).toBe(true)
  })

  it('reject 模式 reason ≥ 5 → confirm 启用 + 提交 reason', async () => {
    mock.onPost('/skills/skill-rv-1/review/reject').reply(200, {
      skill_id: 'skill-rv-1',
      status: 'draft',
      review_state: 'rejected',
      last_action: 'reject',
      last_reviewer_id: 'ou-bob',
      last_reviewed_at: '',
    })
    const onClose = vi.fn()
    _render(
      <ReviewDialog
        skill={_baseSkill()}
        action="reject"
        userId="ou-bob"
        onClose={onClose}
      />,
    )
    fireEvent.change(screen.getByTestId('review-reject-reason-input'), {
      target: { value: '需要更具体的示例步骤' },
    })
    const confirm = screen.getByTestId('review-dialog-confirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)
    await new Promise((r) => setTimeout(r, 50))
    expect(onClose).toHaveBeenCalled()
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.reason).toBe('需要更具体的示例步骤')
  })

  it('取消按钮 → onClose', () => {
    const onClose = vi.fn()
    _render(
      <ReviewDialog
        skill={_baseSkill()}
        action="submit"
        userId="ou-alice"
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByText('取消'))
    expect(onClose).toHaveBeenCalled()
  })
})
