/**
 * PersonNode · v1.2.0 T85 · Knowledge Graph 人物节点.
 *
 * 4 NodeComponent (Person/Event/Concept/Artifact) 都用 shadcn Card 风格 +
 * Lucide icon, 配色统一项目 token (text-text-primary 等).
 */

import { Handle, Position } from '@xyflow/react'
import { User } from 'lucide-react'
import type { KGNode } from '@/types/api'

interface PersonNodeData {
  node: KGNode
  selected?: boolean
}

export function PersonNode({ data }: { data: PersonNodeData }) {
  const { node } = data
  return (
    <div
      data-testid={`kg-node-${node.id}`}
      data-node-type="person"
      className="rounded-md border border-warning bg-warning-bg px-3 py-2 shadow-sm transition hover:shadow-md min-w-[140px] max-w-[200px]"
      title={node.summary || node.label}
    >
      <Handle type="target" position={Position.Left} className="!bg-warning" />
      <div className="flex items-center gap-1.5">
        <User className="size-3.5 shrink-0 text-warning-dark" />
        <span className="line-clamp-1 font-ui text-sm font-medium text-text-primary">
          {node.label}
        </span>
      </div>
      {node.source_event_ids.length > 0 && (
        <div className="mt-1 font-mono text-[10px] text-text-tertiary">
          {node.source_event_ids.length} 事件
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-warning" />
    </div>
  )
}
