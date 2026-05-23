/**
 * ArtifactNode · 文件 / 文档 / Skill / 外部 URL.
 */

import { Handle, Position } from '@xyflow/react'
import { FileText } from 'lucide-react'
import type { KGNode } from '@/types/api'

interface ArtifactNodeData {
  node: KGNode
}

export function ArtifactNode({ data }: { data: ArtifactNodeData }) {
  const { node } = data
  return (
    <div
      data-testid={`kg-node-${node.id}`}
      data-node-type="artifact"
      className="rounded-md border border-border-strong bg-bg-warm px-3 py-2 shadow-sm transition hover:shadow-md min-w-[140px] max-w-[200px]"
      title={node.summary || node.label}
    >
      <Handle type="target" position={Position.Left} className="!bg-text-tertiary" />
      <div className="flex items-center gap-1.5">
        <FileText className="size-3.5 shrink-0 text-text-secondary" />
        <span className="line-clamp-1 font-ui text-sm font-medium text-text-primary">
          {node.label}
        </span>
      </div>
      {node.source_event_ids.length > 0 && (
        <div className="mt-1 font-mono text-[10px] text-text-tertiary">
          {node.source_event_ids.length} 事件
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-text-tertiary" />
    </div>
  )
}
