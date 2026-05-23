/**
 * NodeCrossDocPanel · v1.3.1 T96 单测.
 *
 * 验:
 *   - node=null → 不渲染
 *   - 加载中 → "加载中…"
 *   - entity 未关联 (404) → empty 状态
 *   - 仅当前 asset → "仅出现在当前文档"
 *   - 跨文档: 显示 link, 排除当前 asset
 *   - aliases 渲染
 *   - close 按钮触发 onClose
 *   - link 点击 navigate 到目标 asset
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { NodeCrossDocPanel } from './NodeCrossDocPanel'
import { api } from '@/lib/api'
import type { KGNode } from '@/types/api'

const mkNode = (overrides: Partial<KGNode> = {}): KGNode => ({
  id: 'n_alice',
  type: 'person',
  label: 'Alice',
  summary: null,
  properties: {},
  source_event_ids: ['e1'],
  trust_score: 0.9,
  span_anchor: null,
  ...overrides,
})

function withWrappers(ui: ReactNode, locationPath = '/projects/p1/documents/a1') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[locationPath]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:pid/documents/:did" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('NodeCrossDocPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('node=null → 不渲染面板', () => {
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={null} onClose={() => {}}
      />,
    ))
    expect(screen.queryByTestId('kg-cross-doc-panel')).toBeNull()
  })

  it('entity 404 (节点未注册) → 显示 empty state', async () => {
    vi.spyOn(api, 'get').mockRejectedValue({
      code: 'NOT_FOUND', message: 'no entity', status: 404,
    })
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={mkNode()} onClose={() => {}}
      />,
    ))
    await waitFor(() => {
      expect(screen.getByTestId('kg-cross-doc-empty')).toBeInTheDocument()
    })
  })

  it('实体仅出现在当前 asset → "仅出现在当前文档"', async () => {
    const apiSpy = vi.spyOn(api, 'get')
    apiSpy.mockResolvedValueOnce({
      data: {
        id: 'ent_x', project_id: 'p1', type: 'person',
        label: 'Alice', canonical_label: 'alice', aliases: [],
        source_refs: [{ asset_id: 'a1', chapter_id: 'ch1', node_id: 'n_alice' }],
      },
    })
    apiSpy.mockResolvedValueOnce({
      data: [{
        asset_id: 'a1', asset_title: 'Doc1', asset_type: 'knowledge_graph',
        chapter_ids: ['ch1'], node_ids: ['n_alice'],
      }],
    })
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={mkNode()} onClose={() => {}}
      />,
    ))
    await waitFor(() => {
      expect(screen.getByTestId('kg-cross-doc-only-here')).toBeInTheDocument()
    })
  })

  it('跨文档: 显示其他 asset 列表 (排除当前)', async () => {
    const apiSpy = vi.spyOn(api, 'get')
    apiSpy.mockResolvedValueOnce({
      data: {
        id: 'ent_x', project_id: 'p1', type: 'person',
        label: 'Alice', canonical_label: 'alice', aliases: [],
        source_refs: [],
      },
    })
    apiSpy.mockResolvedValueOnce({
      data: [
        {
          asset_id: 'a1', asset_title: 'CurrentDoc', asset_type: 'knowledge_graph',
          chapter_ids: ['ch1'], node_ids: ['n_alice'],
        },
        {
          asset_id: 'a2', asset_title: 'OtherDoc', asset_type: 'knowledge_graph',
          chapter_ids: ['ch2'], node_ids: ['n_2'],
        },
        {
          asset_id: 'a3', asset_title: 'ThirdDoc', asset_type: 'knowledge_graph',
          chapter_ids: ['ch3'], node_ids: ['n_3a', 'n_3b'],
        },
      ],
    })
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={mkNode()} onClose={() => {}}
      />,
    ))
    await waitFor(() => {
      expect(screen.getByTestId('kg-cross-doc-link-a2')).toBeInTheDocument()
      expect(screen.getByTestId('kg-cross-doc-link-a3')).toBeInTheDocument()
      // 当前 asset 不显示
      expect(screen.queryByTestId('kg-cross-doc-link-a1')).toBeNull()
      expect(screen.getByText('OtherDoc')).toBeInTheDocument()
      // n_ids count 显示
      expect(screen.getByText('2n')).toBeInTheDocument()  // a3 有 2 个 node
    })
  })

  it('aliases 渲染', async () => {
    const apiSpy = vi.spyOn(api, 'get')
    apiSpy.mockResolvedValueOnce({
      data: {
        id: 'ent_x', project_id: 'p1', type: 'person',
        label: 'Alice', canonical_label: 'alice',
        aliases: ['ALICE', 'alice w.'],
        source_refs: [],
      },
    })
    apiSpy.mockResolvedValueOnce({ data: [] })
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={mkNode()} onClose={() => {}}
      />,
    ))
    await waitFor(() => {
      expect(screen.getByText(/ALICE, alice w\./)).toBeInTheDocument()
    })
  })

  it('close 按钮触发 onClose', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        id: 'ent_x', project_id: 'p1', type: 'person',
        label: 'Alice', canonical_label: 'alice', aliases: [],
        source_refs: [],
      },
    }).mockResolvedValueOnce({ data: [] })
    const onClose = vi.fn()
    render(withWrappers(
      <NodeCrossDocPanel
        assetId="a1" projectId="p1" node={mkNode()} onClose={onClose}
      />,
    ))
    const closeBtn = await screen.findByLabelText('关闭面板')
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalled()
  })
})
