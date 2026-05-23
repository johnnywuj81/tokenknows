/**
 * GraphCanvas · v1.2.0 T85 · React Flow 包装 + dagre 自动布局.
 *
 * 入参: KnowledgeGraphLayout (nodes + edges + layout_hints)
 * 行为:
 *   - dagre LR 自动布局 (useMemo 一次性, 同 layout 引用不重算)
 *   - 节点 onClick → 触发 props.onNodeClick (传 node + char_offset)
 *   - 内置 Controls (zoom/pan/fit) + MiniMap
 */

import { useCallback, useMemo } from 'react'
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

const NODE_TYPES: NodeTypes = {
  person: PersonNode,
  event: EventNode,
  concept: ConceptNode,
  artifact: ArtifactNode,
}

const NODE_W = 180
const NODE_H = 60

interface GraphCanvasProps {
  layout: KnowledgeGraphLayout
  onNodeClick?: (node: KGNode) => void
  onEdgeClick?: (edge: KGEdge) => void
  /** v1.2.1 T90: 用于按 asset 维度持久化拖动位置.
   *  null 时不持久化 (e.g. 测试 / 预览态). */
  assetId?: string | null
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
}: GraphCanvasProps) {
  // v1.2.1 T90: 拖动位置持久化 (zustand persist 到 localStorage)
  const storedPositions = usePositionStore((s) =>
    assetId ? s.getPositions(assetId) : {},
  )
  const setPosition = usePositionStore((s) => s.setPosition)

  const { rfNodes, rfEdges } = useMemo(() => {
    const dagrePositions = _runDagreLayout(
      layout.nodes,
      layout.edges,
      layout.layout_hints.rankdir,
    )

    const rfNodes: Node[] = layout.nodes.map((node) => {
      // 优先用 store 中的拖动位置, 否则 dagre 自动布局
      const userPos = storedPositions[node.id]
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
  }, [layout, storedPositions])

  // 拖动结束时保存位置
  const handleNodeDragStop = useCallback<NodeMouseHandler>(
    (_event, node) => {
      if (assetId) {
        setPosition(assetId, node.id, { x: node.position.x, y: node.position.y })
      }
    },
    [assetId, setPosition],
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
