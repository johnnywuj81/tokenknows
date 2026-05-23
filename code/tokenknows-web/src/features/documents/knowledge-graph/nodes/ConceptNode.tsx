/**
 * ConceptNode · 主题词 / 决策 / 抽象概念.
 */

import { Handle, Position } from '@xyflow/react'
import { Lightbulb } from 'lucide-react'
import type { KGNode } from '@/types/api'

interface ConceptNodeData {
  node: KGNode
}

export function ConceptNode({ data }: { data: ConceptNodeData }) {
  const { node } = data
  return (
    <div
      data-testid={`kg-node-${node.id}`}
      data-node-type="concept"
      className="rounded-md border border-accent-primary bg-accent-primary-light px-3 py-2 shadow-sm transition hover:shadow-md min-w-[140px] max-w-[200px]"
      title={node.summary || node.label}
    >
      <Handle type="target" position={Position.Left} className="!bg-accent-primary" />
      <div className="flex items-center gap-1.5">
        <Lightbulb className="size-3.5 shrink-0 text-accent-primary-dark" />
        <span className="line-clamp-1 font-ui text-sm font-medium text-text-primary">
          {node.label}
        </span>
      </div>
      {node.source_event_ids.length > 0 && (
        <div className="mt-1 font-mono text-[10px] text-text-tertiary">
          {node.source_event_ids.length} 事件
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-accent-primary" />
    </div>
  )
}
