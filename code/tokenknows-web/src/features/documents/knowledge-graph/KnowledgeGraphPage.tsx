/**
 * KnowledgeGraphPage · v1.2.0 T86 · 知识图谱资产容器.
 *
 * 路由: DocumentPage 顶部 `if (asset.type === 'knowledge_graph')` 分支进入此页.
 * 读 chapter.layout → KnowledgeGraphLayout, 传给 GraphCanvas.
 */

import { useMemo, useState } from 'react'
import type { Chapter, KGEdge, KGNode, KnowledgeGraphLayout } from '@/types/api'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { GraphCanvas } from './GraphCanvas'
import { GraphSearch } from './GraphSearch'
import { ReviewerNodeTable } from './ReviewerNodeTable'

interface KnowledgeGraphPageProps {
  chapter: Chapter
  onEvidenceJump?: (charOffset: number) => void
}

export default function KnowledgeGraphPage({
  chapter,
  onEvidenceJump,
}: KnowledgeGraphPageProps) {
  const layout = useMemo(() => {
    const raw = chapter.layout as unknown
    if (!raw || typeof raw !== 'object' || !('nodes' in raw)) {
      return null
    }
    return raw as KnowledgeGraphLayout
  }, [chapter.layout])

  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<Set<string>>(
    new Set(['person', 'event', 'concept', 'artifact']),
  )
  const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph')

  const filteredLayout = useMemo<KnowledgeGraphLayout | null>(() => {
    if (!layout) return null
    const q = searchQuery.trim().toLowerCase()
    const filteredNodes = layout.nodes.filter((n) => {
      if (!typeFilter.has(n.type)) return false
      if (!q) return true
      const hay = (n.label + ' ' + (n.summary || '')).toLowerCase()
      return hay.includes(q)
    })
    const validIds = new Set(filteredNodes.map((n) => n.id))
    const filteredEdges = layout.edges.filter(
      (e) => validIds.has(e.source) && validIds.has(e.target),
    )
    return { ...layout, nodes: filteredNodes, edges: filteredEdges }
  }, [layout, searchQuery, typeFilter])

  if (!layout) {
    return (
      <EmptyState
        title="知识图谱数据缺失"
        description="该资产的 chapter.layout 不含有效图谱; 可能仍在生成中或解析失败."
      />
    )
  }

  if (layout.parse_error) {
    return (
      <EmptyState
        title="图谱解析部分失败"
        description={`后端报告: ${layout.parse_error.slice(0, 200)}`}
      />
    )
  }

  function handleNodeClick(node: KGNode): void {
    if (onEvidenceJump && node.span_anchor) {
      onEvidenceJump(node.span_anchor.char_offset)
    }
  }

  function handleEdgeClick(_edge: KGEdge): void {
    // v1.2 MVP: 仅 hover label; v1.3 加 EdgeDetail Drawer
  }

  return (
    <div
      className="flex h-full flex-col"
      data-testid="kg-page"
    >
      <GraphSearch
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        stats={{
          nodeCount: filteredLayout?.nodes.length ?? 0,
          edgeCount: filteredLayout?.edges.length ?? 0,
          totalNodes: layout.nodes.length,
          totalEdges: layout.edges.length,
        }}
      />
      {/* v1.2 T86 · view mode toggle (画布 / Reviewer 节点表) */}
      <div
        className="flex items-center gap-2 border-b border-border-subtle bg-bg-canvas px-4 py-2"
        data-testid="kg-view-toggle"
      >
        <Button
          variant={viewMode === 'graph' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setViewMode('graph')}
          data-testid="kg-view-graph-btn"
        >
          🌐 图谱视图
        </Button>
        <Button
          variant={viewMode === 'table' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setViewMode('table')}
          data-testid="kg-view-table-btn"
        >
          📋 Reviewer 表格
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {viewMode === 'table' && filteredLayout ? (
          <div className="p-4">
            <ReviewerNodeTable layout={filteredLayout} />
          </div>
        ) : filteredLayout && filteredLayout.nodes.length > 0 ? (
          <GraphCanvas
            layout={filteredLayout}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
          />
        ) : (
          <EmptyState
            title="无匹配节点"
            description="试着清空搜索或勾选更多类型."
          />
        )}
      </div>
    </div>
  )
}
