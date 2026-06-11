/**
 * GraphCanvas · v1.2.0 T85 / v1.3 T91 / v1.3.1 T94 · React Flow 包装 + dagre 自动布局 + LOD.
 *
 * 入参: KnowledgeGraphLayout (nodes + edges + layout_hints + user_positions?)
 * 行为:
 *   - 大图 (>100 节点) 自动 LOD 聚类 (T94): 每 type top-20 + 1 supernode
 *   - dagre LR 自动布局 (useMemo 一次性, 同 layout 引用不重算)
 *   - 节点 onClick → 触发 props.onNodeClick (传 node + char_offset)
 *   - supernode onClick → 展开该 type 的所有节点
 *   - 节点拖动 → 写本地 positionStore + debounced PATCH 后端 (T91)
 *   - 位置优先级 (T91): layout.user_positions (server) > positionStore (local) > dagre 自动
 *   - 内置 Controls (zoom/pan/fit) + MiniMap
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type OnNodeDrag,
  type NodeTypes,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'

import type { KGEdge, KGNode, KnowledgeGraphLayout } from '@/types/api'
import { PersonNode } from './nodes/PersonNode'
import { EventNode } from './nodes/EventNode'
import { ConceptNode } from './nodes/ConceptNode'
import { ArtifactNode } from './nodes/ArtifactNode'
import { ClusterNode } from './nodes/ClusterNode'
import { usePositionStore } from './store/positionStore'
import { useChapterPositionsSync } from './store/useChapterPositionsSync'
import { clusterLayout, isSuperNode } from './lod'

const NODE_TYPES: NodeTypes = {
  person: PersonNode,
  event: EventNode,
  concept: ConceptNode,
  artifact: ArtifactNode,
  cluster: ClusterNode,
}

const NODE_W = 180
const NODE_H = 60

interface NodePosition {
  x: number
  y: number
}

/** v1.6 fix · 稳定空对象常量 (避免 selector 返回新 {} 触发 zustand subscribe 死循环). */
const _EMPTY_STORED: Record<string, NodePosition> = Object.freeze({})

/** v1.8 T114 · MiniMap 节点色 (与 thumbnail.py 同色板); cluster 用灰. */
const _MINIMAP_COLOR_BY_TYPE: Record<string, string> = {
  person: '#ca8a04',    // warning-dark (黄)
  event: '#2563eb',     // info-dark (蓝)
  concept: '#16a34a',   // success-dark (绿)
  artifact: '#dc2626',  // danger-dark (红)
  cluster: '#94a3b8',   // tertiary 灰 (supernode)
}

interface GraphCanvasProps {
  layout: KnowledgeGraphLayout
  onNodeClick?: (node: KGNode) => void
  onEdgeClick?: (edge: KGEdge) => void
  /** v1.2.1 T90: 用于按 asset 维度持久化拖动位置.
   *  null 时不持久化 (e.g. 测试 / 预览态). */
  assetId?: string | null
  /** v1.3 T91: chapterId 用于 PATCH /chapters/:id/positions.
   *  null 时仅本地 store; 不写后端. */
  chapterId?: string | null
}

/** Layout 上可能携带 user_positions (server snapshot); 运行时校验 x/y 为数字防御坏数据. */
function _readUserPositions(
  layout: KnowledgeGraphLayout,
): Record<string, NodePosition> | null {
  const raw = layout.user_positions
  if (!raw || typeof raw !== 'object') return null
  const out: Record<string, NodePosition> = {}
  for (const [k, v] of Object.entries(raw)) {
    if (
      v &&
      typeof v === 'object' &&
      typeof v.x === 'number' &&
      typeof v.y === 'number'
    ) {
      out[k] = { x: v.x, y: v.y }
    }
  }
  return Object.keys(out).length ? out : null
}

function _runDagreLayout(
  nodes: KGNode[],
  edges: KGEdge[],
  rankdir: 'LR' | 'TB' | 'BT' | 'RL',
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir, nodesep: 50, ranksep: 80 })

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H })
  }
  for (const e of edges) {
    if (nodes.find((n) => n.id === e.source) && nodes.find((n) => n.id === e.target)) {
      g.setEdge(e.source, e.target)
    }
  }

  dagre.layout(g)

  const positions = new Map<string, { x: number; y: number }>()
  for (const id of g.nodes()) {
    const n = g.node(id)
    positions.set(id, {
      x: n.x - NODE_W / 2,
      y: n.y - NODE_H / 2,
    })
  }
  return positions
}

export function GraphCanvas({
  layout,
  onNodeClick,
  onEdgeClick,
  assetId,
  chapterId,
}: GraphCanvasProps) {
  // v1.2.1 T90: 拖动位置持久化 (zustand persist 到 localStorage)
  // v1.6 fix: selector 不能返回新 {}, 用 stable _EMPTY_STORED 避免死循环
  const storedPositions = usePositionStore((s) =>
    assetId ? s.getPositions(assetId) : _EMPTY_STORED,
  )
  const setPosition = usePositionStore((s) => s.setPosition)
  const hydrateAsset = usePositionStore((s) => s.hydrateAsset)
  // v1.3 T91: 后端同步 hook (debounced PATCH)
  const { sync } = useChapterPositionsSync(assetId ?? null, chapterId ?? null)

  // v1.3.1 T94: LOD 聚类展开状态 (用户点 supernode 可展开该 type)
  const [expandedTypes, setExpandedTypes] = useState<Set<KGNode['type']>>(
    () => new Set(),
  )

  // v1.3 T91: server 的 user_positions 为权威; 进入页面 hydrate 一次到 store
  // 这样跨设备打开能拿到他端拖的位置. 已 hydrate 过的 asset 不重复 hydrate
  // (避免覆盖用户当前拖动中的临时位置).
  const hydratedRef = useRef<Set<string>>(new Set())
  const serverPositions = useMemo(() => _readUserPositions(layout), [layout])
  useEffect(() => {
    if (!assetId) return
    if (!serverPositions) return
    if (hydratedRef.current.has(assetId)) return
    hydratedRef.current.add(assetId)
    hydrateAsset(assetId, serverPositions)
  }, [assetId, serverPositions, hydrateAsset])

  // v1.3.1 T94: LOD 聚类 (>100 节点自动启用)
  const lodResult = useMemo(
    () => clusterLayout(layout, { expanded: expandedTypes }),
    [layout, expandedTypes],
  )

  const { rfNodes, rfEdges } = useMemo(() => {
    // dagre 用聚类后视觉节点跑布局, 避免对隐藏节点空跑
    const dagreNodesForLayout: KGNode[] = lodResult.visibleNodes.map((n) =>
      isSuperNode(n)
        ? ({
            id: n.id,
            type: 'concept',  // dagre 仅用 id, type 占位
            label: n.label,
            summary: null,
            properties: {},
            source_event_ids: [],
            trust_score: n.avg_trust,
            span_anchor: null,
          } satisfies KGNode)
        : n,
    )
    const dagrePositions = _runDagreLayout(
      dagreNodesForLayout,
      lodResult.visibleEdges,
      layout.layout_hints.rankdir,
    )

    const rfNodes: Node[] = lodResult.visibleNodes.map((node) => {
      if (isSuperNode(node)) {
        // supernode 不参与拖动位置持久化 (id 随 cluster 状态变, 不稳定)
        const position = dagrePositions.get(node.id) ?? { x: 0, y: 0 }
        return {
          id: node.id,
          type: 'cluster',
          position,
          data: {
            label: node.label,
            childType: node.child_type,
            count: node.children.length,
            avgTrust: node.avg_trust,
          },
          draggable: false,
        }
      }
      // 普通节点: server.user_positions > 本地 store > dagre
      const fromServer = serverPositions?.[node.id]
      const userPos = fromServer ?? storedPositions[node.id]
      const position = userPos ?? dagrePositions.get(node.id) ?? { x: 0, y: 0 }
      return {
        id: node.id,
        type: node.type,
        position,
        data: { node },
        draggable: true,
      }
    })

    const rfEdges: Edge[] = lodResult.visibleEdges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? edge.type,
      style: {
        strokeWidth: Math.min(4, edge.weight),
        stroke:
          edge.type === 'contradicts'
            ? 'var(--color-danger, #dc2626)'
            : edge.type === 'caused_by'
              ? 'var(--color-warning, #ca8a04)'
              : 'var(--color-text-tertiary, #94a3b8)',
      },
      animated: edge.type === 'contradicts',
      data: { edge },
    }))

    return { rfNodes, rfEdges }
  }, [lodResult, layout.layout_hints.rankdir, storedPositions, serverPositions])

  // 拖动结束时保存位置 (本地 store + debounced PATCH); supernode 不可拖
  const handleNodeDragStop = useCallback<OnNodeDrag>(
    (_event, node) => {
      if (!assetId) return
      if (node.id.startsWith('cluster_')) return
      setPosition(assetId, node.id, { x: node.position.x, y: node.position.y })
      const next = {
        ...usePositionStore.getState().getPositions(assetId),
        [node.id]: { x: node.position.x, y: node.position.y },
      }
      sync(next)
    },
    [assetId, setPosition, sync],
  )

  return (
    <div
      data-testid="kg-graph-canvas"
      className="relative"
      style={{ width: '100%', height: '100%' }}
    >
      {lodResult.clustered ? (
        <div
          data-testid="kg-lod-banner"
          className="absolute right-4 top-4 z-10 rounded-md border border-border-subtle bg-bg-card px-3 py-1.5 font-ui text-caption text-text-secondary shadow-sm"
        >
          🧩 已聚类 {Object.values(lodResult.hiddenByType).reduce((a, b) => a + b, 0)} 个低 trust 节点
          {expandedTypes.size > 0 ? (
            <button
              type="button"
              data-testid="kg-lod-collapse-all"
              className="ml-2 text-accent-primary hover:underline"
              onClick={() => setExpandedTypes(new Set())}
            >
              全部折叠
            </button>
          ) : null}
        </div>
      ) : null}
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => {
          // supernode: 展开该 type
          if (n.type === 'cluster') {
            const data = n.data as { childType?: KGNode['type'] }
            const t = data?.childType
            if (t) {
              setExpandedTypes((prev) => {
                const next = new Set(prev)
                next.add(t)
                return next
              })
            }
            return
          }
          const kgNode = (n.data as { node?: KGNode })?.node
          if (kgNode && onNodeClick) {
            onNodeClick(kgNode)
          }
        }}
        onNodeDragStop={handleNodeDragStop}
        onEdgeClick={(_, e) => {
          const kgEdge = (e.data as { edge?: KGEdge })?.edge
          if (kgEdge && onEdgeClick) {
            onEdgeClick(kgEdge)
          }
        }}
      >
        <Background />
        <Controls />
        {/* v1.8 T116 · 小图 (≤30 节点) 不显示 MiniMap (3 节点缩到 1px 看着像
            白板, 反而干扰). 大图启用 + 自定义着色. */}
        {rfNodes.length > 30 ? (
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) =>
              _MINIMAP_COLOR_BY_TYPE[n.type as string] ?? '#94a3b8'
            }
            nodeStrokeColor={(n) =>
              _MINIMAP_COLOR_BY_TYPE[n.type as string] ?? '#475569'
            }
            nodeStrokeWidth={4}
            maskColor="rgba(15, 23, 42, 0.12)"
            style={{
              backgroundColor: '#f5f5f4',
              border: '1px solid #e7e5e4',
            }}
          />
        ) : null}
      </ReactFlow>
    </div>
  )
}
