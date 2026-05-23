/**
 * GraphSearch · v1.2.0 T85 · 顶部搜索框 + 4 类型 checkbox + 统计.
 */

import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import type { KGNodeType } from '@/types/api'

interface GraphSearchProps {
  searchQuery: string
  onSearchChange: (q: string) => void
  typeFilter: Set<string>
  onTypeFilterChange: (next: Set<string>) => void
  stats: {
    nodeCount: number
    edgeCount: number
    totalNodes: number
    totalEdges: number
  }
}

const TYPES: { value: KGNodeType; label: string; colorClass: string }[] = [
  { value: 'person', label: '人物', colorClass: 'text-warning-dark' },
  { value: 'event', label: '事件', colorClass: 'text-info' },
  { value: 'concept', label: '概念', colorClass: 'text-accent-primary-dark' },
  { value: 'artifact', label: '产物', colorClass: 'text-text-secondary' },
]

export function GraphSearch({
  searchQuery,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  stats,
}: GraphSearchProps) {
  function toggleType(t: string): void {
    const next = new Set(typeFilter)
    if (next.has(t)) next.delete(t)
    else next.add(t)
    onTypeFilterChange(next)
  }

  return (
    <div
      className="flex flex-col gap-2 border-b border-border-subtle bg-bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid="kg-graph-search"
    >
      <div className="flex flex-1 items-center gap-2">
        <Search className="size-4 shrink-0 text-text-tertiary" />
        <Input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="按标签 / 摘要搜索节点"
          data-testid="kg-search-input"
          className="max-w-md"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {TYPES.map((t) => (
          <label
            key={t.value}
            className="flex items-center gap-1.5 cursor-pointer"
            data-testid={`kg-filter-${t.value}`}
          >
            <Checkbox
              checked={typeFilter.has(t.value)}
              onCheckedChange={() => toggleType(t.value)}
            />
            <span className={`font-ui text-sm ${t.colorClass}`}>{t.label}</span>
          </label>
        ))}
        <span
          className="font-mono text-xs text-text-tertiary"
          data-testid="kg-stats"
        >
          {stats.nodeCount}/{stats.totalNodes} 节点 · {stats.edgeCount}/{stats.totalEdges} 边
        </span>
      </div>
    </div>
  )
}
