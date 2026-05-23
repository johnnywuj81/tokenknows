/**
 * GovernancePage · v0.8 T64 unit tests.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import GovernancePage from './GovernancePage'

const mock = new MockAdapter(api)

function _render(initialPath = '/projects/p-1/skills/governance') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route
            path="/projects/:id/skills/governance"
            element={<GovernancePage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mock.reset()
})

describe('GovernancePage', () => {
  it('error 状态 → ErrorState', async () => {
    mock.onGet('/projects/p-1/skills/governance').reply(500)
    _render()
    await waitFor(() =>
      expect(screen.getByText(/加载 Skill 治理失败/)).toBeInTheDocument(),
    )
  })

  it('正常 → 渲染 stats + candidate cards', async () => {
    mock.onGet('/projects/p-1/skills/governance').reply(200, {
      project_id: 'p-1',
      total: 10,
      by_status: { active: 5, draft: 2, deprecated: 3 },
      by_review_state: { approved: 5, pending_review: 1, not_submitted: 4 },
      evolve_candidates: 2,
      dormant_candidates: 1,
      low_trust_candidates: 3,
      avg_trust_score: 0.65,
    })
    _render()
    await waitFor(() =>
      expect(screen.getByTestId('governance-stats')).toBeInTheDocument(),
    )
    // 总数
    expect(screen.getByText('10')).toBeInTheDocument()
    // active count
    expect(screen.getByText('5')).toBeInTheDocument()
    // candidates
    expect(screen.getByText(/2 待 Evolve|🌱 待 Evolve/)).toBeInTheDocument()
    // 平均 trust 65%
    expect(screen.getByText('65%')).toBeInTheDocument()
  })

  it('立即跑 trust recompute → 调 endpoint', async () => {
    mock.onGet('/projects/p-1/skills/governance').reply(200, {
      project_id: 'p-1',
      total: 0,
      by_status: {},
      by_review_state: {},
      evolve_candidates: 0,
      dormant_candidates: 0,
      low_trust_candidates: 0,
      avg_trust_score: 0,
    })
    mock
      .onPost('/projects/p-1/skills/governance/run-trust-recompute')
      .reply(200, { scanned: 5, updated: 2, skipped: 3 })
    _render()
    await waitFor(() =>
      expect(screen.getByTestId('trust-recompute-btn')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('trust-recompute-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('trust-result')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('trust-result').textContent).toContain('scanned=5')
    expect(screen.getByTestId('trust-result').textContent).toContain('updated=2')
  })

  it('立即跑 deprecation sweep → 显示结果', async () => {
    mock.onGet('/projects/p-1/skills/governance').reply(200, {
      project_id: 'p-1',
      total: 0,
      by_status: {},
      by_review_state: {},
      evolve_candidates: 0,
      dormant_candidates: 0,
      low_trust_candidates: 0,
      avg_trust_score: 0,
    })
    mock
      .onPost('/projects/p-1/skills/governance/run-deprecation-sweep')
      .reply(200, { remaining_candidates: 0 })
    _render()
    await waitFor(() =>
      expect(screen.getByTestId('deprecation-sweep-btn')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('deprecation-sweep-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('deprecation-result')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('deprecation-result').textContent).toContain('0')
  })

  it('header + 帮助文字渲染', async () => {
    mock.onGet('/projects/p-1/skills/governance').reply(200, {
      project_id: 'p-1',
      total: 0,
      by_status: {},
      by_review_state: {},
      evolve_candidates: 0,
      dormant_candidates: 0,
      low_trust_candidates: 0,
      avg_trust_score: 0,
    })
    _render()
    await waitFor(() =>
      expect(screen.getByText('Skill 治理看板')).toBeInTheDocument(),
    )
    expect(screen.getByText(/每日自动跑/)).toBeInTheDocument()
  })
})
