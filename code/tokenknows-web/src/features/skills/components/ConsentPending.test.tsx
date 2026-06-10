/**
 * ConsentPending banner · v0.5.1 T51 unit tests.
 *
 * 覆盖:
 *   - status != pending → 不渲染
 *   - status == pending → 渲染
 *   - 当前用户 ∈ required + 未签 → 显示 sign/reject 按钮
 *   - 当前用户 ∈ required + 已签 → 不显示按钮, 显示 "你已同意"
 *   - 当前用户 ∉ required → 不显示按钮
 *   - 待签人数 / 截止时间 文案正确
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Skill } from '@/types/api'
import { ConsentPending } from './ConsentPending'
import { useAuthStore } from '@/stores/authStore'

function _baseSkill(overrides: Partial<Skill> = {}): Skill {
  const now = new Date().toISOString()
  return {
    id: 'skill-test-1',
    project_id: 'proj-X',
    name: 'pr-summary-formatting',
    version: 1,
    skill_md: '---\nname: x\n---\n# body',
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
    status: 'pending_contributor_consent',
    parent_skill_id: null,
    contributors: ['ou-alice', 'ou-bob'],
    consent_required_from: ['ou-alice', 'ou-bob'],
    consent_signed_by: [],
    consent_rejected_by: null,
    consent_expires_at: '2026-06-22T00:00:00Z',
    review_state: 'not_submitted',
    review_history: [],
    last_reviewer_id: null,
    last_reviewed_at: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  }
}

function _renderWithProviders(ui: React.ReactNode) {
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
        created_at: '2026-01-01',
        updated_at: '2026-01-01',
      }
    : null
  useAuthStore.setState({
    user,
    accessToken: id ? 'fake' : null,
    isAuthenticated: !!id,
  })
}

describe('ConsentPending banner', () => {
  it('不渲染 when status != pending', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({ status: 'active' })
    const { container } = _renderWithProviders(
      <ConsentPending skill={skill} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('渲染 banner with 待签 N/M · 截止 date', () => {
    _setUser('ou-alice')
    const skill = _baseSkill()
    _renderWithProviders(<ConsentPending skill={skill} />)
    expect(screen.getByTestId('consent-pending-banner')).toBeInTheDocument()
    expect(screen.getByText(/还差 2\/2 contributor/)).toBeInTheDocument()
  })

  it('当前 contributor 未签 → 显示 sign/reject 按钮', () => {
    _setUser('ou-alice')
    const skill = _baseSkill()
    _renderWithProviders(<ConsentPending skill={skill} />)
    expect(screen.getByTestId('consent-sign-btn')).toBeInTheDocument()
    expect(screen.getByTestId('consent-reject-btn')).toBeInTheDocument()
  })

  it('当前 contributor 已签 → 不显示按钮 + 显示 "你已同意"', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({
      consent_signed_by: [
        {
          user_id: 'ou-alice',
          signed_at: '2026-05-23T10:00:00Z',
          channel: 'web',
          note: null,
        },
      ],
    })
    _renderWithProviders(<ConsentPending skill={skill} />)
    expect(screen.queryByTestId('consent-sign-btn')).toBeNull()
    expect(screen.queryByTestId('consent-reject-btn')).toBeNull()
    expect(screen.getByText(/你已同意/)).toBeInTheDocument()
  })

  it('非 contributor 用户 → 不显示按钮', () => {
    _setUser('ou-rogue')
    const skill = _baseSkill()
    _renderWithProviders(<ConsentPending skill={skill} />)
    // banner 仍渲染 (任何人可看进度)
    expect(screen.getByTestId('consent-pending-banner')).toBeInTheDocument()
    // 但按钮不可见
    expect(screen.queryByTestId('consent-sign-btn')).toBeNull()
    expect(screen.queryByTestId('consent-reject-btn')).toBeNull()
  })

  it('1/2 已签 → 待签 1/2', () => {
    _setUser('ou-bob')
    const skill = _baseSkill({
      consent_signed_by: [
        {
          user_id: 'ou-alice',
          signed_at: '2026-05-23T10:00:00Z',
          channel: 'web',
          note: null,
        },
      ],
    })
    _renderWithProviders(<ConsentPending skill={skill} />)
    expect(screen.getByText(/还差 1\/2 contributor/)).toBeInTheDocument()
    // bob 未签, 仍可见按钮
    expect(screen.getByTestId('consent-sign-btn')).toBeInTheDocument()
  })

  it('expires_at null → 截止显示 "—"', () => {
    _setUser('ou-alice')
    const skill = _baseSkill({ consent_expires_at: null })
    _renderWithProviders(<ConsentPending skill={skill} />)
    expect(screen.getByText(/截止 —/)).toBeInTheDocument()
  })
})
