/**
 * GraphCanvas · v1.2.0 T85 / v1.3 T91 · React Flow 包装 + dagre 自动布局.
 *
 * 入参: KnowledgeGraphLayout (nodes + edges + layout_hints + user_positions?)
 * 行为:
 *   - dagre LR 自动布局 (useMemo 一次性, 同 layout 引用不重算)
 *   - 节点 onClick → 触发 props.onNodeClick (传 node + char_offset)
 *   - 节点拖动 → 写本地 positionStore + debounced PATCH 后端 (T91)
 *   - 位置优先级 (T91): layout.user_positions (server) > positionStore (local) > dagre 自动
 *   - 内置 Controls (zoom/pan/fit) + MiniMap
 */

import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'

import type { KGEdge, KGNode, KnowledgeGraphLayout } from '@/types/api'
import { PersonNode } from './nodes/PersonNode'
import { EventNode } from './nodes/EventNode'
import { ConceptNode } from './nodes/ConceptNode'
import { ArtifactNode } from './nodes/ArtifactNode'
import { usePositionStore } from './store/positionStore'
import { useChapterPositionsSync } from './store/useChapterPositionsSync'

const NODE_TYPES: NodeTypes = {
  person: PersonNode,
  event: EventNode,
  concept: ConceptNode,
  artifact: ArtifactNode,
}

const NODE_W = 180
const NODE_H = 60

interface NodePosition {
  x: number
  y: number
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
  const storedPositions = usePositionStore((s) =>
    assetId ? s.getPositions(assetId) : {},
  )
  const setPosition = usePositionStore((s) => s.setPosition)
  const hydrateAsset = usePositionStore((s) => s.hydrateAsset)
  // v1.3 T91: 后端同步 hook (debounced PATCH)
  const { sync } = useChapterPositionsSync(assetId ?? null, chapterId ?? null)

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

  const { rfNodes, rfEdges } = useMemo(() => {
    const dagrePositions = _runDagreLayout(
      layout.nodes,
      layout.edges,
      layout.layout_hints.rankdir,
    )

    const rfNodes: Node[] = layout.nodes.map((node) => {
      // 优先级: server.user_positions > 本地 store > dagre 自动
      // (server hydrate 后 storedPositions 也会拿到同样值, 但 server 派发先于 store update)
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

    const rfEdges: Edge[] = layout.edges.map((edge) => ({
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
  }, [layout, storedPositions, serverPositions])

  // 拖动结束时保存位置 (本地 store + debounced PATCH)
  const handleNodeDragStop = useCallback<NodeMouseHandler>(
    (_event, node) => {
      if (!assetId) return
      setPosition(assetId, node.id, { x: node.position.x, y: node.position.y })
      // T91: PATCH 整套 snapshot (latest store state after this set)
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
      style={{ width: '100%', height: '100%' }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => {
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
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  )
}
