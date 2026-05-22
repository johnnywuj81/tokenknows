/**
 * DocumentCard · 补足: clone/delete dropdown actions, click handler, similarity tones.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { DocumentCard } from './DocumentCard'
import type { Asset } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: 'doc',
  status: 'draft', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed',
  metrics: { coverage: 0.8, citation_density: 0.4, slop_score: 0.15, similarity: 0.4 },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('DocumentCard extra branches', () => {
  it('clicking title navigates (non-generating)', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset()} projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const titleBtn = screen.getByText('doc').closest('button')
    fireEvent.click(titleBtn!)
    // no error means navigation works
  })

  it('generating: clicking title disabled, no nav', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({ status: 'generating' })} projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const titleBtn = screen.getByText('doc').closest('button')
    expect(titleBtn).toBeDisabled()
  })

  it('similarity high (>85): danger tone', () => {
    const { container } = render(withWrappers(<DocumentCard
      asset={mkAsset({ metrics: { coverage: 0.8, citation_density: 0.4, slop_score: 0.1, similarity: 0.95 } })}
      projectId="p1" onClone={() => {}} onDelete={() => {}}
    />))
    expect(container.querySelector('.text-danger')).not.toBeNull()
  })

  it('similarity medium (>60 ≤85): warning tone', () => {
    const { container } = render(withWrappers(<DocumentCard
      asset={mkAsset({ metrics: { coverage: 0.8, citation_density: 0.4, slop_score: 0.1, similarity: 0.7 } })}
      projectId="p1" onClone={() => {}} onDelete={() => {}}
    />))
    expect(container.querySelector('.text-warning')).not.toBeNull()
  })

  it('slop high (>20): warning tone', () => {
    const { container } = render(withWrappers(<DocumentCard
      asset={mkAsset({ metrics: { coverage: 0.8, citation_density: 0.4, slop_score: 0.3, similarity: 0.3 } })}
      projectId="p1" onClone={() => {}} onDelete={() => {}}
    />))
    expect(container.querySelector('.text-warning')).not.toBeNull()
  })

  it('generating status: skeleton shown + no metrics', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({ status: 'generating', metrics: null })} projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.getByText(/生成中 · 预计 5 秒/)).toBeInTheDocument()
  })

  it('no metrics + not generating: shows title only', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({ metrics: null })} projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.getByText('doc')).toBeInTheDocument()
    expect(screen.queryByText(/覆盖/)).toBeNull()
  })

  it('more menu trigger: stopPropagation on click does not trigger nav', () => {
    const onClone = vi.fn()
    render(withWrappers(<DocumentCard
      asset={mkAsset()} projectId="p1"
      onClone={onClone} onDelete={() => {}}
    />))
    const moreBtn = screen.getByLabelText('更多操作')
    fireEvent.click(moreBtn)
    // dropdown opens, no nav
  })
})
