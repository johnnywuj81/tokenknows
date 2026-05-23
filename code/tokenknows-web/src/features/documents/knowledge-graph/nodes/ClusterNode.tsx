/**
 * ClusterNode · v1.3.1 T94 · LOD 聚类元节点.
 *
 * 显示 "其他 N 个 <type>", 点击触发 GraphCanvas 内部 expandedTypes 状态切换
 * (展开后该 type 的 supernode 不再生成).
 */

import { Handle, Position } from '@xyflow/react'
import { Layers } from 'lucide-react'
import type { KGNode } from '@/types/api'

interface ClusterNodeData {
  label: string
  childType: KGNode['type']
  count: number
  avgTrust: number
}

export function ClusterNode({ data }: { data: ClusterNodeData }) {
  const { label, childType, count, avgTrust } = data
  return (
    <div
      data-testid={`kg-cluster-${childType}`}
      data-node-type="cluster"
      data-child-type={childType}
      className="rounded-md border-2 border-dashed border-text-tertiary bg-bg-warm px-3 py-2 shadow-sm transition hover:shadow-md hover:border-accent-primary cursor-pointer min-w-[140px] max-w-[220px]"
      title={`展开 ${count} 个 ${childType} (平均 trust ${avgTrust.toFixed(2)})`}
    >
      <Handle type="target" position={Position.Left} className="!bg-text-tertiary" />
      <div className="flex items-center gap-1.5">
        <Layers className="size-3.5 shrink-0 text-text-tertiary" />
        <span className="line-clamp-1 font-ui text-sm font-medium text-text-secondary">
          {label}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-text-tertiary">
        <span>点击展开</span>
        <span>⌀ {avgTrust.toFixed(2)}</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-text-tertiary" />
    </div>
  )
}
