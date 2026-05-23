/**
 * EventNode · PR / commit / incident / IM 群消息.
 */

import { Handle, Position } from '@xyflow/react'
import { Zap } from 'lucide-react'
import type { KGNode } from '@/types/api'

interface EventNodeData {
  node: KGNode
}

export function EventNode({ data }: { data: EventNodeData }) {
  const { node } = data
  return (
    <div
      data-testid={`kg-node-${node.id}`}
      data-node-type="event"
      className="rounded-md border border-info bg-info-bg px-3 py-2 shadow-sm transition hover:shadow-md min-w-[140px] max-w-[200px]"
      title={node.summary || node.label}
    >
      <Handle type="target" position={Position.Left} className="!bg-info" />
      <div className="flex items-center gap-1.5">
        <Zap className="size-3.5 shrink-0 text-info" />
        <span className="line-clamp-1 font-ui text-sm font-medium text-text-primary">
          {node.label}
        </span>
      </div>
      {node.source_event_ids.length > 0 && (
        <div className="mt-1 font-mono text-[10px] text-text-tertiary">
          {node.source_event_ids.length} 事件
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-info" />
    </div>
  )
}
