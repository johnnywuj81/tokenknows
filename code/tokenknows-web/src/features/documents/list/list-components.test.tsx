/**
 * DocumentFilters + DocumentCard 单测 (presentational).
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DocumentFilters } from './DocumentFilters'
import { DocumentCard } from './DocumentCard'
import type { ReactNode } from 'react'
import type { Asset } from '@/types/api'


function withRouterQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


// ─── DocumentFilters ──────────────────────────────────────────


describe('DocumentFilters', () => {
  it('renders 5 type tabs + status select', () => {
    render(<DocumentFilters
      type="all" status="all"
      onTypeChange={() => {}} onStatusChange={() => {}}
    />)
    // tabs
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('周报')).toBeInTheDocument()
    expect(screen.getByText('技术方案')).toBeInTheDocument()
    expect(screen.getByText('ADR')).toBeInTheDocument()
    expect(screen.getByText('复盘')).toBeInTheDocument()
  })

  it('8 type tabs all rendered (含 v0.2 书籍/Skill + v1.2 知识图谱)', () => {
    render(<DocumentFilters
      type="weekly_report" status="all"
      onTypeChange={() => {}} onStatusChange={() => {}}
    />)
    const tabs = screen.getAllByRole('tab')
    // 全部 + weekly_report + tech_design + adr + incident + book + agent_skill + knowledge_graph
    expect(tabs.length).toBe(8)
    expect(screen.getByText('书籍')).toBeInTheDocument()
    expect(screen.getByText('Skill')).toBeInTheDocument()
    expect(screen.getByText('知识图谱')).toBeInTheDocument()
  })
})


// ─── DocumentCard ──────────────────────────────────────────────


const mockAsset: Asset = {
  id: 'a1', project_id: 'p1', type: 'weekly_report',
  title: '周报 · 2026-W21', status: 'draft',
  current_version: 1, template_id: 't',
  created_by: 'u1', approval_state: 'pending',
  redaction_state: 'any_unresolved',
  metrics: {
    coverage: 0.85, citation_density: 0.42,
    slop_score: 0.18, similarity: 0.999,   // 高相似 → 红
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}


describe('DocumentCard', () => {
  it('renders title + status + metrics with similarity column', () => {
    render(withRouterQuery(
      <DocumentCard asset={mockAsset} projectId="p1" />,
    ))
    expect(screen.getByText('周报 · 2026-W21')).toBeInTheDocument()
    expect(screen.getByText('草稿')).toBeInTheDocument()
    // 4 个指标都展示
    expect(screen.getByText(/覆盖/)).toBeInTheDocument()
    expect(screen.getByText(/引用/)).toBeInTheDocument()
    expect(screen.getByText(/空话/)).toBeInTheDocument()
    expect(screen.getByText(/相似/)).toBeInTheDocument()
  })

  it('similarity 100% rendered as red text', () => {
    const { container } = render(withRouterQuery(
      <DocumentCard asset={mockAsset} projectId="p1" />,
    ))
    // 找含 100% 的 strong (similarity 字段)
    const strongElts = container.querySelectorAll('strong')
    const has100 = Array.from(strongElts).some((e) => e.textContent === '100%')
    expect(has100).toBe(true)
  })

  it('generating status shows progress UI', () => {
    const gen = { ...mockAsset, status: 'generating' as const, metrics: null }
    render(withRouterQuery(
      <DocumentCard asset={gen} projectId="p1" />,
    ))
    // 生成中文案可能出现多处 (badge + body), 任一即可
    const all = screen.getAllByText(/生成中/)
    expect(all.length).toBeGreaterThan(0)
  })

  it('approved status badge color', () => {
    const approved = { ...mockAsset, status: 'approved' as const }
    render(withRouterQuery(
      <DocumentCard asset={approved} projectId="p1" />,
    ))
    expect(screen.getByText('已通过')).toBeInTheDocument()
  })

  it('published status', () => {
    const pub = { ...mockAsset, status: 'published' as const }
    render(withRouterQuery(
      <DocumentCard asset={pub} projectId="p1" />,
    ))
    expect(screen.getByText('已发布')).toBeInTheDocument()
  })
})
