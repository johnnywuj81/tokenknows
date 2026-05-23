/**
 * ReviewerNodeTable · v1.2.0 T86 · Reviewer 视图.
 *
 * Reviewer 不审 markdown 而是审节点表; 不在画布上直接 approve/reject,
 * 整 asset reject 走现有 DocHeader 按钮.
 *
 * 列: id / type / label / source_events count / trust_score / 可疑标记
 *
 * 静态截图 (Playwright headless) 留 v1.3.
 */

import { useState } from 'react'
import type { KGNode, KnowledgeGraphLayout } from '@/types/api'

interface ReviewerNodeTableProps {
  layout: KnowledgeGraphLayout
  onMarkSuspect?: (nodeId: string) => void
}

const TYPE_COLOR: Record<string, string> = {
  person: 'text-warning-dark',
  event: 'text-info',
  concept: 'text-accent-primary-dark',
  artifact: 'text-text-secondary',
}

export function ReviewerNodeTable({
  layout,
  onMarkSuspect,
}: ReviewerNodeTableProps) {
  const [suspectIds, setSuspectIds] = useState<Set<string>>(new Set())

  function toggleSuspect(nodeId: string): void {
    const next = new Set(suspectIds)
    if (next.has(nodeId)) next.delete(nodeId)
    else next.add(nodeId)
    setSuspectIds(next)
    onMarkSuspect?.(nodeId)
  }

  return (
    <section
      data-testid="reviewer-node-table"
      className="rounded-md border border-border-subtle bg-bg-card"
    >
      <header className="border-b border-border-subtle px-4 py-3">
        <h3 className="font-content text-base font-semibold text-text-primary">
          📋 节点审计表 ({layout.nodes.length})
        </h3>
        <p className="font-ui text-xs text-text-secondary">
          勾选可疑节点以标记; Reviewer 见疑可整图退回 (用上方"退回"按钮).
        </p>
      </header>
      <table className="w-full font-ui text-sm">
        <thead className="border-b border-border-subtle bg-bg-warm">
          <tr className="text-left text-caption text-text-muted">
            <th className="px-3 py-2 w-8"></th>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">类型</th>
            <th className="px-3 py-2">标签</th>
            <th className="px-3 py-2 text-right">事件数</th>
            <th className="px-3 py-2 text-right">置信度</th>
          </tr>
        </thead>
        <tbody>
          {layout.nodes.map((n: KGNode) => {
            const isSuspect = suspectIds.has(n.id)
            return (
              <tr
                key={n.id}
                data-testid={`reviewer-row-${n.id}`}
                className={`border-b border-border-subtle last:border-b-0 ${
                  isSuspect ? 'bg-danger-bg' : ''
                }`}
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={isSuspect}
                    onChange={() => toggleSuspect(n.id)}
                    aria-label={`标记 ${n.label} 为可疑`}
                    data-testid={`reviewer-suspect-${n.id}`}
                  />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-text-tertiary">
                  {n.id}
                </td>
                <td className={`px-3 py-2 ${TYPE_COLOR[n.type]}`}>
                  {n.type}
                </td>
                <td className="px-3 py-2 text-text-primary">{n.label}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {n.source_event_ids.length}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {Math.round(n.trust_score * 100)}%
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {suspectIds.size > 0 && (
        <footer
          className="border-t border-border-subtle px-4 py-2 font-mono text-xs text-danger"
          data-testid="reviewer-suspect-count"
        >
          已标记 {suspectIds.size} 个可疑节点
        </footer>
      )}
    </section>
  )
}
