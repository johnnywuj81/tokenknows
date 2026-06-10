/**
 * KnowledgeGraphPage · v1.2 T85 unit tests.
 *
 * 注: React Flow 需要 ResizeObserver (jsdom 无); 这里只测容器层逻辑
 * (layout 解析 / 搜索过滤 / parse_error 分支), 真画布渲染留 e2e (Playwright).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Chapter, KnowledgeGraphLayout } from '@/types/api'
import KnowledgeGraphPage from './KnowledgeGraphPage'

// Mock GraphCanvas (React Flow 在 jsdom 内部出错)
vi.mock('./GraphCanvas', () => ({
  GraphCanvas: ({ layout }: { layout: KnowledgeGraphLayout }) => (
    <div data-testid="kg-graph-canvas">
      Canvas: {layout.nodes.length} nodes, {layout.edges.length} edges
    </div>
  ),
}))

beforeEach(() => {
  // ResizeObserver polyfill 兜底 (即使被 mock 也以防 React Flow 间接引用)
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
})

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function _chapter(layout: KnowledgeGraphLayout | object | null): Chapter {
  return {
    id: 'ch-1',
    asset_id: 'a-1',
    asset_version: 1,
    order_index: 0,
    parent_id: null,
    depth: 0,
    title: '实体关系图谱',
    content: '# 实体关系图谱',
    layout: layout as Record<string, unknown>,
    generated_by: null,
    regeneration_history: [],
    applied_skills: [],
    approval_state: 'pending',
    redacted_spans: [],
  }
}

function _baseLayout(): KnowledgeGraphLayout {
  return {
    schema_version: 'kg.v1',
    nodes: [
      {
        id: 'n_alice', type: 'person', label: 'Alice',
        summary: 'JWT 决策的发起人',
        properties: { im_user_id: 'ou-alice' },
        source_event_ids: ['e1'],
        trust_score: 0.8,
        span_anchor: { char_offset: 10 },
      },
      {
        id: 'n_jwt', type: 'concept', label: 'JWT 迁移',
        properties: {}, source_event_ids: ['e1', 'e2'],
        trust_score: 0.85,
      },
      {
        id: 'n_pr', type: 'event', label: 'PR #127',
        properties: {}, source_event_ids: ['e1'],
        trust_score: 0.7,
      },
    ],
    edges: [
      {
        id: 'edge_1', source: 'n_pr', target: 'n_alice',
        type: 'authored_by', label: 'PR #127 by Alice',
        weight: 2, source_event_ids: ['e1'],
      },
      {
        id: 'edge_2', source: 'n_pr', target: 'n_jwt',
        type: 'mentions', label: '讨论 JWT', weight: 1,
        source_event_ids: ['e1'],
      },
    ],
    layout_hints: { algorithm: 'dagre', rankdir: 'LR' },
    parse_error: null,
    raw_output: null,
  }
}

describe('KnowledgeGraphPage', () => {
  it('layout 缺失 → 提示数据缺失', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(null)} />)
    expect(screen.getByText(/知识图谱数据缺失/)).toBeInTheDocument()
  })

  it('layout 非法 (无 nodes 键) → 数据缺失', () => {
    _render(<KnowledgeGraphPage chapter={_chapter({ foo: 'bar' })} />)
    expect(screen.getByText(/知识图谱数据缺失/)).toBeInTheDocument()
  })

  it('parse_error → 显示解析失败 + 报告', () => {
    const layout = _baseLayout()
    layout.parse_error = 'JSONDecodeError: line 5'
    _render(<KnowledgeGraphPage chapter={_chapter(layout)} />)
    expect(screen.getByText(/图谱解析部分失败/)).toBeInTheDocument()
    expect(screen.getByText(/JSONDecodeError/)).toBeInTheDocument()
  })

  it('正常 layout → 渲染 Canvas + Search', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    expect(screen.getByTestId('kg-page')).toBeInTheDocument()
    expect(screen.getByTestId('kg-graph-canvas')).toBeInTheDocument()
    expect(screen.getByTestId('kg-graph-search')).toBeInTheDocument()
    // stats 显示
    expect(screen.getByTestId('kg-stats').textContent).toContain('3/3 节点')
    expect(screen.getByTestId('kg-stats').textContent).toContain('2/2 边')
  })

  it('搜索过滤: 输入 "pr" → 只剩 PR 节点 (label 含 pr)', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    fireEvent.change(screen.getByTestId('kg-search-input'), {
      target: { value: 'pr' },
    })
    // 只 n_pr label "PR #127" 含 pr; n_jwt/n_alice 都不含
    expect(screen.getByTestId('kg-stats').textContent).toContain('1/3 节点')
    // PR 节点没有指向其他被过滤节点的边 → 0
    expect(screen.getByTestId('kg-stats').textContent).toContain('0/2 边')
  })

  it('搜索过滤: 跨 label + summary 双字段搜', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    fireEvent.change(screen.getByTestId('kg-search-input'), {
      target: { value: 'jwt' },
    })
    // n_jwt label 含 + n_alice summary 含 → 2 节点命中
    expect(screen.getByTestId('kg-stats').textContent).toContain('2/3 节点')
  })

  it('type filter: 取消 person → 不再包含 Alice', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    // 取消 person 勾选
    fireEvent.click(screen.getByTestId('kg-filter-person').querySelector('button')!)
    // 节点 3 → 2 (剩 jwt + pr)
    expect(screen.getByTestId('kg-stats').textContent).toContain('2/3 节点')
    // edge_1 (pr → alice) 因 alice 被过滤 → 失效
    expect(screen.getByTestId('kg-stats').textContent).toContain('1/2 边')
  })

  it('所有 type 都过滤掉 → 显示无匹配节点', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    for (const t of ['person', 'event', 'concept', 'artifact']) {
      fireEvent.click(screen.getByTestId(`kg-filter-${t}`).querySelector('button')!)
    }
    expect(screen.getByText(/无匹配节点/)).toBeInTheDocument()
  })

  it('节点点击触发 onNodeClick (T88 抛节点给父组件)', () => {
    const onNodeClick = vi.fn()
    _render(
      <KnowledgeGraphPage
        chapter={_chapter(_baseLayout())}
        onNodeClick={onNodeClick}
      />,
    )
    expect(screen.getByTestId('kg-page')).toBeInTheDocument()
    // GraphCanvas 被 mock, 实际 click 不触发; 仅 smoke 验 prop 接受
  })

  it('view mode 切换: 默认 graph, 点 table → ReviewerNodeTable', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    expect(screen.getByTestId('kg-graph-canvas')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('kg-view-table-btn'))
    expect(screen.getByTestId('reviewer-node-table')).toBeInTheDocument()
    expect(screen.getByTestId('reviewer-row-n_alice')).toBeInTheDocument()
    expect(screen.getByTestId('reviewer-row-n_jwt')).toBeInTheDocument()
    expect(screen.getByTestId('reviewer-row-n_pr')).toBeInTheDocument()
  })

  it('Reviewer 标记可疑节点显示计数 + 行变红', () => {
    _render(<KnowledgeGraphPage chapter={_chapter(_baseLayout())} />)
    fireEvent.click(screen.getByTestId('kg-view-table-btn'))
    fireEvent.click(screen.getByTestId('reviewer-suspect-n_alice'))
    expect(
      screen.getByTestId('reviewer-suspect-count').textContent,
    ).toContain('1 个可疑节点')
    const row = screen.getByTestId('reviewer-row-n_alice')
    expect(row.className).toContain('bg-danger-bg')
  })
})
