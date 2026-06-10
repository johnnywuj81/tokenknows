/**
 * ReviewActions · v0.6.0 T58 unit tests.
 *
 * 覆盖 4 个 review_state 分支 + 按钮可见性:
 * - status=active → 不渲染
 * - draft + not_submitted → 提交审批按钮 (contributor 可见)
 * - pending_review → approve/reject 按钮
 * - approved → ✅ badge
 * - rejected → ❌ badge + reason + 重新提交
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Skill } from '@/types/api'
import { ReviewActions } from './ReviewActions'
import { useAuthStore } from '@/stores/authStore'

function _baseSkill(overrides: Partial<Skill> = {}): Skill {
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
    contributors: ['ou-alice', 'ou-bob'],
    consent_required_from: [],
    consent_signed_by: [],
    consent_rejected_by: null,
    consent_expires_at: null,
    review_state: 'not_submitted',
    review_history: [],
    last_reviewer_id: null,
    last_reviewed_at: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  }
}

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function _setUser(id: string | null) {
  const user = id
    ? {
        id,
        email: `${id}@x`,
        display_name: id,
        is_instance_admin: false,
        email_verified_at: null,
        created_at: '',
        updated_at: '',
      }
    : null
  useAuthStore.setState({
    user,
    accessToken: id ? 'fake' : null,
    isAuthenticated: !!id,
  })
}

describe('ReviewActions', () => {
  it('不渲染 when status=active 且 review_state=not_submitted', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({ status: 'active' })
    const { container } = _render(<ReviewActions skill={skill} />)
    expect(container.firstChild).toBeNull()
  })

  it('draft + not_submitted + contributor → 显示提交按钮', () => {
    _setUser('ou-alice')
    const skill = _baseSkill()
    _render(<ReviewActions skill={skill} />)
    expect(screen.getByTestId('review-actions')).toBeInTheDocument()
    expect(screen.getByTestId('review-submit-btn')).toBeInTheDocument()
  })

  it('draft + not_submitted + 非 contributor → 不显示按钮', () => {
    _setUser('ou-stranger')
    const skill = _baseSkill()
    _render(<ReviewActions skill={skill} />)
    expect(screen.queryByTestId('review-submit-btn')).toBeNull()
  })

  it('pending_review → 显示 approve/reject 按钮', () => {
    _setUser('ou-bob')
    const skill = _baseSkill({
      review_state: 'pending_review',
      review_history: [
        {
          reviewer_id: 'ou-alice',
          action: 'submit',
          timestamp: '2026-06-01T00:00:00Z',
          note: null,
        },
      ],
    })
    _render(<ReviewActions skill={skill} />)
    expect(screen.getByTestId('review-approve-btn')).toBeInTheDocument()
    expect(screen.getByTestId('review-reject-btn')).toBeInTheDocument()
  })

  it('approved → 显示 ✅ badge + reviewer', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({
      status: 'active',
      review_state: 'approved',
      last_reviewer_id: 'ou-bob',
      last_reviewed_at: '2026-06-02T00:00:00Z',
    })
    _render(<ReviewActions skill={skill} />)
    expect(screen.getByText(/已批准/)).toBeInTheDocument()
    expect(screen.getByText(/ou-bob/)).toBeInTheDocument()
  })

  it('rejected → 显示 ❌ badge + reason + 重新提交按钮', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({
      review_state: 'rejected',
      last_reviewer_id: 'ou-bob',
      last_reviewed_at: '2026-06-02T00:00:00Z',
      review_history: [
        {
          reviewer_id: 'ou-alice',
          action: 'submit',
          timestamp: '2026-06-01T00:00:00Z',
          note: null,
        },
        {
          reviewer_id: 'ou-bob',
          action: 'reject',
          timestamp: '2026-06-02T00:00:00Z',
          note: '需要更多具体例子',
        },
      ],
    })
    _render(<ReviewActions skill={skill} />)
    expect(screen.getByText(/已退回/)).toBeInTheDocument()
    expect(screen.getByTestId('review-reject-reason').textContent).toContain(
      '需要更多具体例子',
    )
    expect(screen.getByTestId('review-resubmit-btn')).toBeInTheDocument()
  })

  it('rejected + 非 contributor → 不显示重新提交按钮', () => {
    _setUser('ou-stranger')
    const skill = _baseSkill({
      review_state: 'rejected',
      last_reviewer_id: 'ou-bob',
      last_reviewed_at: '2026-06-02T00:00:00Z',
      review_history: [],
    })
    _render(<ReviewActions skill={skill} />)
    expect(screen.queryByTestId('review-resubmit-btn')).toBeNull()
  })
})
