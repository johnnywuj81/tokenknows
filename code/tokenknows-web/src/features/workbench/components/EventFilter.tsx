/**
 * EventFilter · 事件流筛选(source_type)
 *
 * MVP: 仅 source 维度 5 选 1(含"全部")。
 * 后续可扩展 author / event_type 等多维。
 */

import { Filter } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { EventSourceType } from '@/types/api'

interface EventFilterProps {
  sourceType: EventSourceType | null
  onChange: (s: EventSourceType | null) => void
}

const OPTIONS: { value: EventSourceType; label: string }[] = [
  { value: 'claude_code', label: 'Claude Code' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'vscode', label: 'VS Code' },
  { value: 'github', label: 'GitHub' },
  { value: 'local_file', label: '本地文件' },
]

export function EventFilter({ sourceType, onChange }: EventFilterProps) {
  const activeLabel = sourceType
    ? OPTIONS.find((o) => o.value === sourceType)?.label
    : null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md border border-border-subtle bg-bg-card px-2.5 py-1 font-ui text-caption text-text-secondary transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          <Filter className="size-3.5 text-text-muted" />
          {activeLabel ?? '全部来源'}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          按来源筛选
        </DropdownMenuLabel>
        <DropdownMenuCheckboxItem
          checked={sourceType === null}
          onCheckedChange={() => onChange(null)}
          className="font-ui text-body-sm"
        >
          全部来源
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        {OPTIONS.map((o) => (
          <DropdownMenuCheckboxItem
            key={o.value}
            checked={sourceType === o.value}
            onCheckedChange={() => onChange(sourceType === o.value ? null : o.value)}
            className="font-ui text-body-sm"
          >
            {o.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
