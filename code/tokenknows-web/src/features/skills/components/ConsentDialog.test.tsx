/**
 * ConsentDialog · v0.5.1 T51 unit tests.
 *
 * 覆盖:
 *   - sign 模式: confirm 直接调 mutation; 关闭后 onClose 调
 *   - reject 模式: reason < 5 字符 → confirm disabled; ≥ 5 字符 → enabled
 *   - reason ≥ 5 字符 confirm → mutation 调; 显示提交中状态
 *   - 取消按钮 → onClose 调
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import type { Skill } from '@/types/api'
import { ConsentDialog } from './ConsentDialog'

const mock = new MockAdapter(api)

function _baseSkill(): Skill {
  const now = new Date().toISOString()
  return {
    id: 'skill-test-1',
    project_id: 'proj-X',
    name: 'demo',
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
    status: 'pending_contributor_consent',
    parent_skill_id: null,
    contributors: ['ou-alice'],
    consent_required_from: ['ou-alice'],
    consent_signed_by: [],
    consent_rejected_by: null,
    consent_expires_at: now,
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

describe('ConsentDialog', () => {
  it('sign 模式: confirm 调 sign endpoint', async () => {
    mock.onPost('/skills/skill-test-1/consent/sign').reply(200, {
      skill_id: 'skill-test-1',
      current_status: 'draft',
      signed_count: 1,
      required_count: 1,
      all_signed: true,
    })
    const onClose = vi.fn()
    _render(
      <ConsentDialog
        skill={_baseSkill()}
        action="sign"
        userId="ou-alice"
        onClose={onClose}
      />,
    )
    expect(screen.getByText(/同意发布该 Skill/)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('consent-dialog-confirm'))
    // 等异步完成
    await new Promise((r) => setTimeout(r, 50))
    expect(onClose).toHaveBeenCalled()
    expect(mock.history.post.length).toBe(1)
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.user_id).toBe('ou-alice')
    expect(body.channel).toBe('web')
  })

  it('reject 模式: reason < 5 → confirm disabled', () => {
    _render(
      <ConsentDialog
        skill={_baseSkill()}
        action="reject"
        userId="ou-alice"
        onClose={vi.fn()}
      />,
    )
    const confirm = screen.getByTestId('consent-dialog-confirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(true)

    const input = screen.getByTestId('reject-reason-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'no' } })
    expect(confirm.disabled).toBe(true)
  })

  it('reject 模式: reason ≥ 5 → confirm enabled + 调 endpoint', async () => {
    mock.onPost('/skills/skill-test-1/consent/reject').reply(200, {
      skill_id: 'skill-test-1',
      current_status: 'rejected_by_contributor',
      rejected_by: 'ou-alice',
    })
    const onClose = vi.fn()
    _render(
      <ConsentDialog
        skill={_baseSkill()}
        action="reject"
        userId="ou-alice"
        onClose={onClose}
      />,
    )
    fireEvent.change(screen.getByTestId('reject-reason-input'), {
      target: { value: '属于 HR 私下讨论' },
    })
    const confirm = screen.getByTestId('consent-dialog-confirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)
    await new Promise((r) => setTimeout(r, 50))
    expect(onClose).toHaveBeenCalled()
    expect(mock.history.post.length).toBe(1)
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.reason).toBe('属于 HR 私下讨论')
  })

  it('取消按钮 → onClose', () => {
    const onClose = vi.fn()
    _render(
      <ConsentDialog
        skill={_baseSkill()}
        action="sign"
        userId="ou-alice"
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByText('取消'))
    expect(onClose).toHaveBeenCalled()
  })

  it('reject 字符计数 显示 X / 500', () => {
    _render(
      <ConsentDialog
        skill={_baseSkill()}
        action="reject"
        userId="ou-alice"
        onClose={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByTestId('reject-reason-input'), {
      target: { value: 'hello' },
    })
    expect(screen.getByText('5 / 500')).toBeInTheDocument()
  })
})
