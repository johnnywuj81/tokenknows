/**
 * EvolveChain · v0.8.0 T63 · Skill 进化链横向 timeline.
 *
 * 显示 parent → current → children 节点 (按 version 升序);
 * 仅 1 个节点时不渲染 (无进化历史).
 */

import type { SkillEvolveChainNode } from '@/types/api'
import { useSkillEvolveChain } from '../hooks/useSkills'

interface EvolveChainProps {
  skillId: string
}

const STATUS_COLOR: Record<string, string> = {
  active: 'bg-success-bg text-success-dark',
  draft: 'bg-warning-bg text-warning-dark',
  pending_contributor_consent: 'bg-warning-bg text-warning-dark',
  deprecated: 'bg-bg-canvas text-text-tertiary',
  locked: 'bg-bg-canvas text-text-tertiary',
  rejected_by_contributor: 'bg-danger-bg text-danger',
  expired_no_consent: 'bg-danger-bg text-danger',
}

export function EvolveChain({ skillId }: EvolveChainProps) {
  const q = useSkillEvolveChain(skillId)

  if (q.isLoading || q.isError) return null
  const nodes = q.data?.nodes ?? []
  if (nodes.length <= 1) return null  // 无进化历史不显示

  return (
    <section
      data-testid="evolve-chain"
      aria-label="Skill 进化链"
      className="rounded-md border border-border-subtle bg-bg-canvas p-4"
    >
      <h3 className="mb-3 font-ui text-sm font-medium text-text-secondary">
        🌱 进化历史 ({nodes.length} 个版本)
      </h3>
      <div className="flex flex-wrap items-center gap-1.5">
        {nodes.map((n, i) => (
          <ChainNode key={n.skill_id} node={n} isLast={i === nodes.length - 1} />
        ))}
      </div>
    </section>
  )
}

function ChainNode({
  node,
  isLast,
}: {
  node: SkillEvolveChainNode
  isLast: boolean
}) {
  const color = STATUS_COLOR[node.status] ?? 'bg-bg-canvas text-text-tertiary'
  return (
    <>
      <div
        data-testid={`chain-node-${node.skill_id}`}
        data-current={node.is_current}
        className={`flex items-center gap-1 rounded px-2 py-1 ${color} ${
          node.is_current ? 'ring-2 ring-accent-primary ring-offset-1' : ''
        }`}
      >
        <span className="font-mono text-xs font-medium">v{node.version}</span>
        <span className="font-ui text-xs">{node.name}</span>
        {node.is_current && (
          <span className="font-mono text-[10px] uppercase">current</span>
        )}
      </div>
      {!isLast && (
        <span className="font-mono text-text-tertiary" aria-hidden>
          →
        </span>
      )}
    </>
  )
}
