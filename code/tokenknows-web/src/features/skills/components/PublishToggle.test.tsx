/**
 * PublishToggle · v1.0 T70 unit tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import type { Skill } from '@/types/api'
import { PublishToggle } from './PublishToggle'

const mock = new MockAdapter(api)

function _baseSkill(overrides: Partial<Skill> = {}): Skill {
  const now = new Date().toISOString()
  return {
    id: 's-pub-1',
    project_id: 'p-1',
    name: 'demo',
    version: 1,
    skill_md: '---\n---\n',
    embedding: null,
    metrics: {
      usage_count: 10,
      acceptance_count: 8,
      rejection_count: 2,
      avg_acceptance_rate: 0.8,
      trust_score: 0.7,
    },
    distilled_from: [],
    distilled_at: now,
    last_used_at: now,
    locked: false,
    status: 'active',
    parent_skill_id: null,
    contributors: [],
    consent_required_from: [],
    consent_signed_by: [],
    consent_rejected_by: null,
    consent_expires_at: null,
    review_state: 'approved',
    review_history: [],
    last_reviewer_id: null,
    last_reviewed_at: null,
    visibility: 'private',
    published_at: null,
    source_skill_id: null,
    source_project_id: null,
    imported_at: null,
    created_at: now,
    updated_at: now,
    ...overrides,
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

describe('PublishToggle', () => {
  it('non-active + private → 不渲染', () => {
    const skill = _baseSkill({ status: 'draft', visibility: 'private' })
    const { container } = _render(<PublishToggle skill={skill} />)
    expect(container.firstChild).toBeNull()
  })

  it('approved + active + private → 显示发布按钮', () => {
    const skill = _baseSkill()
    _render(<PublishToggle skill={skill} />)
    expect(screen.getByTestId('publish-toggle')).toBeInTheDocument()
    expect(screen.getByText('发布到市场')).toBeInTheDocument()
  })

  it('public → 显示撤回按钮 + published_at', () => {
    const skill = _baseSkill({
      visibility: 'public',
      published_at: '2026-06-01T10:00:00Z',
    })
    _render(<PublishToggle skill={skill} />)
    expect(screen.getByText('🌐 已发布到市场')).toBeInTheDocument()
    expect(screen.getByText('撤回')).toBeInTheDocument()
    expect(screen.getByText(/published_at/)).toBeInTheDocument()
  })

  it('点击发布 → POST /publish', async () => {
    mock.onPost('/skills/s-pub-1/publish').reply(200, {
      skill_id: 's-pub-1',
      visibility: 'public',
      published_at: '2026-06-01',
    })
    _render(<PublishToggle skill={_baseSkill()} />)
    fireEvent.click(screen.getByTestId('publish-toggle-btn'))
    await waitFor(() => expect(mock.history.post.length).toBe(1))
    expect(mock.history.post[0].url).toBe('/skills/s-pub-1/publish')
  })

  it('点击撤回 → POST /unpublish', async () => {
    mock.onPost('/skills/s-pub-1/unpublish').reply(200, {
      skill_id: 's-pub-1',
      visibility: 'private',
      published_at: null,
    })
    _render(
      <PublishToggle
        skill={_baseSkill({
          visibility: 'public',
          published_at: '2026-06-01',
        })}
      />,
    )
    fireEvent.click(screen.getByTestId('publish-toggle-btn'))
    await waitFor(() => expect(mock.history.post.length).toBe(1))
    expect(mock.history.post[0].url).toBe('/skills/s-pub-1/unpublish')
  })

  it('publish 失败显示 error', async () => {
    mock.onPost('/skills/s-pub-1/publish').reply(403, {
      detail: 'Only project owner can publish',
    })
    _render(<PublishToggle skill={_baseSkill()} />)
    fireEvent.click(screen.getByTestId('publish-toggle-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('publish-error')).toBeInTheDocument(),
    )
  })
})
