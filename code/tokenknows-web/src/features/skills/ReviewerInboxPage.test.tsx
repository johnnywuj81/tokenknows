/**
 * ReviewerInboxPage · v0.6.0 T58 unit tests.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import ReviewerInboxPage from './ReviewerInboxPage'

const mock = new MockAdapter(api)

function _render(initialPath = '/projects/p-1/skills/review-inbox') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route
            path="/projects/:id/skills/review-inbox"
            element={<ReviewerInboxPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mock.reset()
})

describe('ReviewerInboxPage', () => {
  it('empty 列表 → 显示 EmptyState', async () => {
    mock.onGet('/projects/p-1/skills/pending-review').reply(200, [])
    _render()
    await waitFor(() =>
      expect(screen.getByText(/没有待审批/)).toBeInTheDocument(),
    )
  })

  it('多 skill → 全部渲染', async () => {
    const now = new Date().toISOString()
    mock.onGet('/projects/p-1/skills/pending-review').reply(200, [
      {
        id: 's-1',
        project_id: 'p-1',
        name: 'skill-1',
        version: 1,
        skill_md: '',
        embedding: null,
        metrics: {
          usage_count: 0, acceptance_count: 0, rejection_count: 0,
          avg_acceptance_rate: 0, trust_score: 0.5,
        },
        distilled_from: [],
        distilled_at: now,
        last_used_at: null,
        locked: false,
        status: 'draft',
        parent_skill_id: null,
        contributors: ['ou-a'],
        consent_required_from: [],
        consent_signed_by: [],
        consent_rejected_by: null,
        consent_expires_at: null,
        review_state: 'pending_review',
        review_history: [
          {
            reviewer_id: 'ou-a',
            action: 'submit',
            timestamp: now,
            note: null,
          },
        ],
        last_reviewer_id: null,
        last_reviewed_at: null,
        created_at: now,
        updated_at: now,
      },
      {
        id: 's-2',
        project_id: 'p-1',
        name: 'skill-2',
        version: 1,
        skill_md: '',
        embedding: null,
        metrics: {
          usage_count: 0, acceptance_count: 0, rejection_count: 0,
          avg_acceptance_rate: 0, trust_score: 0.5,
        },
        distilled_from: [],
        distilled_at: now,
        last_used_at: null,
        locked: false,
        status: 'draft',
        parent_skill_id: null,
        contributors: ['ou-b', 'ou-c'],
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
      },
    ])
    _render()
    await waitFor(() =>
      expect(screen.getByTestId('reviewer-inbox-list')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('reviewer-inbox-item-s-1')).toBeInTheDocument()
    expect(screen.getByTestId('reviewer-inbox-item-s-2')).toBeInTheDocument()
    expect(screen.getByText('skill-1')).toBeInTheDocument()
    expect(screen.getByText('skill-2')).toBeInTheDocument()
  })

  it('error → 显示 ErrorState', async () => {
    mock.onGet('/projects/p-1/skills/pending-review').reply(500, {
      detail: 'boom',
    })
    _render()
    await waitFor(() =>
      expect(screen.getByText(/加载待审 Skill 失败/)).toBeInTheDocument(),
    )
  })
})
