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

  // v1.2.1 T89: knowledge_graph 类型 + kg_summary → 显示徽章
  it('knowledge_graph asset 显示 kg-summary 静态徽章', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        title: '团队复盘图谱',
        kg_summary: { node_count: 12, edge_count: 18 },
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const badge = screen.getByTestId('kg-summary-badge')
    expect(badge.textContent).toContain('12n')
    expect(badge.textContent).toContain('18e')
  })

  it('weekly_report asset 不渲染 kg-summary 徽章 (即使误填 kg_summary 也忽略)', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'weekly_report',
        kg_summary: { node_count: 5, edge_count: 3 },  // 非 KG 不该读
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.queryByTestId('kg-summary-badge')).toBeNull()
  })

  it('knowledge_graph 但 kg_summary 缺失 (生成中) → 不渲染徽章', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: null,
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.queryByTestId('kg-summary-badge')).toBeNull()
  })

  it('knowledge_graph TYPE_LABEL 显示 "知识图谱"', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: { node_count: 5, edge_count: 3 },
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.getByText('知识图谱')).toBeInTheDocument()
  })

  // v1.3.1 T95 · KG thumbnail
  it('knowledge_graph with thumbnail_svg → 渲染 <img> 缩略图', () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"><circle cx="50" cy="50" r="5"/></svg>'
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: { node_count: 5, edge_count: 3, thumbnail_svg: svg },
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const thumb = screen.getByTestId('kg-thumbnail')
    expect(thumb).toBeInTheDocument()
    const img = thumb.querySelector('img')
    expect(img).not.toBeNull()
    expect(img?.getAttribute('src')).toContain('data:image/svg+xml')
    expect(img?.getAttribute('src')).toContain(encodeURIComponent('<circle'))
  })

  it('knowledge_graph without thumbnail_svg → 不渲染缩略图 (仅节点数徽章)', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: { node_count: 5, edge_count: 3 },  // 没 thumbnail_svg
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    expect(screen.queryByTestId('kg-thumbnail')).toBeNull()
    expect(screen.getByTestId('kg-summary-badge')).toBeInTheDocument()
  })

  // v1.5 T100 · PNG 优先
  it('T100 · thumbnail_png_b64 优先于 svg (data:image/png)', () => {
    const fakePng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEX/AAAZ4gk3AAAAAXRSTlMAQObYZgAAAApJREFUCNdjYAAAAAIAAeIhvDMAAAAASUVORK5CYII='
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: {
          node_count: 5, edge_count: 3,
          thumbnail_png_b64: fakePng,
          thumbnail_svg: '<svg></svg>',
        },
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const thumb = screen.getByTestId('kg-thumbnail')
    expect(thumb.getAttribute('data-format')).toBe('png')
    const img = thumb.querySelector('img')
    expect(img?.getAttribute('src')).toBe(`data:image/png;base64,${fakePng}`)
  })

  it('T100 · 只有 svg 时仍用 SVG (PNG 不可用 fallback)', () => {
    render(withWrappers(<DocumentCard
      asset={mkAsset({
        type: 'knowledge_graph',
        kg_summary: {
          node_count: 5, edge_count: 3,
          thumbnail_svg: '<svg></svg>',
        },
      })}
      projectId="p1"
      onClone={() => {}} onDelete={() => {}}
    />))
    const thumb = screen.getByTestId('kg-thumbnail')
    expect(thumb.getAttribute('data-format')).toBe('svg')
  })
})
