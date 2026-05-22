/**
 * DocumentFilters · 类型 tab + 状态 select
 *
 * filter 走 URL query (设计依据 TaskTechDesign T05: Zustand 无, 用 URL query)。
 */

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AssetStatus, AssetType } from '@/types/api'

interface DocumentFiltersProps {
  type: AssetType | 'all'
  status: AssetStatus | 'all'
  onTypeChange: (t: AssetType | 'all') => void
  onStatusChange: (s: AssetStatus | 'all') => void
}

const TYPE_OPTIONS: { value: AssetType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'weekly_report', label: '周报' },
  { value: 'tech_design', label: '技术方案' },
  { value: 'adr', label: 'ADR' },
  { value: 'incident', label: '复盘' },
  { value: 'book', label: '书籍' }, // v0.2: 长文档 (10万字+ 嵌套大纲)
]

const STATUS_OPTIONS: { value: AssetStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'in_review', label: '审批中' },
  { value: 'approved', label: '已通过' },
  { value: 'published', label: '已发布' },
  { value: 'archived', label: '已归档' },
]

export function DocumentFilters({
  type,
  status,
  onTypeChange,
  onStatusChange,
}: DocumentFiltersProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <Tabs value={type} onValueChange={(v) => onTypeChange(v as AssetType | 'all')}>
        <TabsList className="flex-wrap">
          {TYPE_OPTIONS.map((o) => (
            <TabsTrigger key={o.value} value={o.value} className="font-ui text-body-sm">
              {o.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <Select
        value={status}
        onValueChange={(v) => onStatusChange(v as AssetStatus | 'all')}
      >
        <SelectTrigger className="w-32 font-ui text-body-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {STATUS_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value} className="font-ui text-body-sm">
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
