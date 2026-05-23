/**
 * EvolveChain · v0.8 T63 unit tests.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import { EvolveChain } from './EvolveChain'

const mock = new MockAdapter(api)

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  )
}

beforeEach(() => {
  mock.reset()
})

describe('EvolveChain', () => {
  it('单节点不渲染 (无进化历史)', async () => {
    mock.onGet('/skills/s-1/evolve-chain').reply(200, {
      skill_id: 's-1',
      nodes: [
        {
          skill_id: 's-1',
          name: 'demo',
          version: 1,
          status: 'active',
          parent_skill_id: null,
          created_at: '2026-01-01',
          is_current: true,
        },
      ],
    })
    const { container } = _render(<EvolveChain skillId="s-1" />)
    await waitFor(() =>
      expect(container.querySelector('[data-testid="evolve-chain"]')).toBeNull(),
    )
  })

  it('多节点渲染 + current 标记 + → 分隔', async () => {
    mock.onGet('/skills/s-v2/evolve-chain').reply(200, {
      skill_id: 's-v2',
      nodes: [
        {
          skill_id: 's-v1',
          name: 'demo',
          version: 1,
          status: 'deprecated',
          parent_skill_id: null,
          created_at: '2026-01-01',
          is_current: false,
        },
        {
          skill_id: 's-v2',
          name: 'demo',
          version: 2,
          status: 'active',
          parent_skill_id: 's-v1',
          created_at: '2026-02-01',
          is_current: true,
        },
      ],
    })
    _render(<EvolveChain skillId="s-v2" />)
    await waitFor(() =>
      expect(screen.getByTestId('evolve-chain')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('chain-node-s-v1')).toBeInTheDocument()
    expect(screen.getByTestId('chain-node-s-v2')).toBeInTheDocument()
    // current 标记
    const v2 = screen.getByTestId('chain-node-s-v2')
    expect(v2.getAttribute('data-current')).toBe('true')
    expect(screen.getByText('current')).toBeInTheDocument()
  })

  it('error 静默不渲染', async () => {
    mock.onGet('/skills/s-err/evolve-chain').reply(500)
    const { container } = _render(<EvolveChain skillId="s-err" />)
    await waitFor(() =>
      expect(container.querySelector('[data-testid="evolve-chain"]')).toBeNull(),
    )
  })

  it('版本号 v1 / v2 显示', async () => {
    mock.onGet('/skills/s-2/evolve-chain').reply(200, {
      skill_id: 's-2',
      nodes: [
        {
          skill_id: 's-1',
          name: 'pr-summary',
          version: 1,
          status: 'deprecated',
          parent_skill_id: null,
          created_at: '2026-01-01',
          is_current: false,
        },
        {
          skill_id: 's-2',
          name: 'pr-summary',
          version: 2,
          status: 'active',
          parent_skill_id: 's-1',
          created_at: '2026-02-01',
          is_current: true,
        },
      ],
    })
    _render(<EvolveChain skillId="s-2" />)
    await waitFor(() =>
      expect(screen.getByText('v1')).toBeInTheDocument(),
    )
    expect(screen.getByText('v2')).toBeInTheDocument()
  })

  it('header 显示节点数量', async () => {
    mock.onGet('/skills/s-3/evolve-chain').reply(200, {
      skill_id: 's-3',
      nodes: Array.from({ length: 3 }, (_, i) => ({
        skill_id: `s-v${i + 1}`,
        name: 'demo',
        version: i + 1,
        status: i === 2 ? 'active' : 'deprecated',
        parent_skill_id: i === 0 ? null : `s-v${i}`,
        created_at: '2026-01-01',
        is_current: i === 2,
      })),
    })
    _render(<EvolveChain skillId="s-3" />)
    await waitFor(() =>
      expect(screen.getByText(/3 个版本/)).toBeInTheDocument(),
    )
  })
})
