/**
 * KnowledgeGraphView · v1.2.1 T88 unit tests.
 *
 * 验证 onNodeClick → 按 node.source_event_ids 找匹配 evidence → openEvidence(chapterId, evidenceId).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import type { Asset, Chapter, Evidence, KGNode } from '@/types/api'
import { KnowledgeGraphView } from './KnowledgeGraphView'

const mock = new MockAdapter(api)

// Mock KnowledgeGraphPage 以便我们直接测 onNodeClick wire-up
vi.mock('./KnowledgeGraphPage', () => ({
  __esModule: true,
  default: ({ onNodeClick }: { onNodeClick: (n: KGNode) => void }) => (
    <div data-testid="kg-page-mock">
      <button
        data-testid="trigger-node-with-event-1"
        onClick={() =>
          onNodeClick({
            id: 'n_alice',
            type: 'person',
            label: 'Alice',
            properties: {},
            source_event_ids: ['evt-1'],
            trust_score: 0.8,
          })
        }
      >
        click node alice
      </button>
      <button
        data-testid="trigger-node-no-match"
        onClick={() =>
          onNodeClick({
            id: 'n_orphan',
            type: 'concept',
            label: '孤儿节点',
            properties: {},
            source_event_ids: ['evt-nonexistent'],
            trust_score: 0.5,
          })
        }
      >
        click orphan node
      </button>
    </div>
  ),
}))

// Mock DocHeader 避免 PublishDialog 等复杂依赖
vi.mock('../page/components/DocHeader', () => ({
  DocHeader: () => <div data-testid="doc-header-mock">DocHeader</div>,
}))

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function _asset(): Asset {
  return {
    id: 'a-kg-1',
    project_id: 'p-1',
    type: 'knowledge_graph',
    title: 'JWT 迁移图谱',
    status: 'draft',
    current_version: 1,
    template_id: null,
    created_by: 'u',
    approval_state: 'pending',
    redaction_state: 'all_confirmed',
    metrics: null,
    created_at: '',
    updated_at: '',
  }
}

function _chapter(): Chapter {
  return {
    id: 'ch-kg-1',
    asset_id: 'a-kg-1',
    asset_version: 1,
    order_index: 0,
    parent_id: null,
    depth: 0,
    title: '实体关系图谱',
    content: '# 实体关系图谱',
    layout: {},
    generated_by: null,
    regeneration_history: [],
    applied_skills: [],
    approval_state: 'pending',
    redacted_spans: [],
  }
}

function _evidences(): Evidence[] {
  return [
    {
      id: 'ev-1',
      chapter_id: 'ch-kg-1',
      event_id: 'evt-1',
      event_version: 1,
      span_start: 0,
      span_end: 10,
      citation_text: 'PR #127',
      manually_added: false,
      stale: false,
      event_preview: {
        event_id: 'evt-1',
        title: null,
        author_name: null,
        author_email: null,
        source_type: 'github_pr',
        source_ref: 'github.com/x/repo/pull/127',
        occurred_at: '',
        content_excerpt: '',
        external_url: null,
      },
    },
    {
      id: 'ev-2',
      chapter_id: 'ch-kg-1',
      event_id: 'evt-2',
      event_version: 1,
      span_start: 0,
      span_end: 10,
      citation_text: 'IM 讨论',
      manually_added: false,
      stale: false,
      event_preview: {
        event_id: 'evt-2',
        title: null,
        author_name: null,
        author_email: null,
        source_type: 'im_message',
        source_ref: '',
        occurred_at: '',
        content_excerpt: '',
        external_url: null,
      },
    },
  ]
}

beforeEach(() => {
  mock.reset()
})

describe('KnowledgeGraphView', () => {
  it('match: 节点 source_event_ids 含 evidence.event_id → openEvidence(chapterId, evidenceId)', async () => {
    mock
      .onGet('/assets/a-kg-1/chapters/ch-kg-1/evidence')
      .reply(200, _evidences())
    // KnowledgeGraphView 新挂了 EvidenceDrawer + PublishDialog (后者 usePublishRecords
    // 会立即拉 publish-records) — 给个 200 空数组避免 axios-mock-adapter 拒绝
    mock.onGet('/assets/a-kg-1/publish-records').reply(200, [])

    const onOpen = vi.fn()
    _render(
      <KnowledgeGraphView
        asset={_asset()}
        chapter={_chapter()}
        onSubmit={vi.fn()}
        submitting={false}
        onPublish={vi.fn()}
        onOpenEvidence={onOpen}
      />,
    )
    await waitFor(() =>
      expect(screen.getByTestId('kg-page-mock')).toBeInTheDocument(),
    )
    // 等 evidence URL 至少被请求一次 (PublishDialog 等其它挂件也会发请求, 不锁死总数)
    await waitFor(() =>
      expect(
        mock.history.get.some((c) =>
          (c.url ?? '').endsWith('/chapters/ch-kg-1/evidence'),
        ),
      ).toBe(true),
    )
    // 触发匹配 click
    screen.getByTestId('trigger-node-with-event-1').click()
    await waitFor(() => expect(onOpen).toHaveBeenCalled())
    expect(onOpen).toHaveBeenCalledWith('ch-kg-1', 'ev-1')
  })

  it('no match: 节点无 evidence 关联 → openEvidence(chapterId, undefined) (fallback)', async () => {
    mock
      .onGet('/assets/a-kg-1/chapters/ch-kg-1/evidence')
      .reply(200, _evidences())
    mock.onGet('/assets/a-kg-1/publish-records').reply(200, [])

    const onOpen = vi.fn()
    _render(
      <KnowledgeGraphView
        asset={_asset()}
        chapter={_chapter()}
        onSubmit={vi.fn()}
        submitting={false}
        onPublish={vi.fn()}
        onOpenEvidence={onOpen}
      />,
    )
    await waitFor(() =>
      expect(
        mock.history.get.some((c) =>
          (c.url ?? '').endsWith('/chapters/ch-kg-1/evidence'),
        ),
      ).toBe(true),
    )
    screen.getByTestId('trigger-node-no-match').click()
    await waitFor(() => expect(onOpen).toHaveBeenCalled())
    expect(onOpen).toHaveBeenCalledWith('ch-kg-1', undefined)
  })

  it('evidence load 中: 节点 click 走 fallback (undefined evidence id)', async () => {
    // 不 mock GET, 让 query pending
    let resolveReq: (v: Evidence[]) => void = () => {}
    mock.onGet('/assets/a-kg-1/chapters/ch-kg-1/evidence').reply(
      () =>
        new Promise((resolve) => {
          resolveReq = (v) => resolve([200, v])
        }),
    )

    const onOpen = vi.fn()
    _render(
      <KnowledgeGraphView
        asset={_asset()}
        chapter={_chapter()}
        onSubmit={vi.fn()}
        submitting={false}
        onPublish={vi.fn()}
        onOpenEvidence={onOpen}
      />,
    )
    // 不等 load 完成, 直接 click → fallback (空 evidences 数组 → 无匹配)
    await waitFor(() =>
      expect(screen.getByTestId('kg-page-mock')).toBeInTheDocument(),
    )
    screen.getByTestId('trigger-node-with-event-1').click()
    expect(onOpen).toHaveBeenCalledWith('ch-kg-1', undefined)
    resolveReq([])  // cleanup
  })
})
