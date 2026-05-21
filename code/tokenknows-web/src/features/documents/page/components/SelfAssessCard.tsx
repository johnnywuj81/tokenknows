/**
 * SelfAssessCard · 文档自评卡 4 指标
 *
 * 任务包 T06: "顶部恒显: 覆盖度 / 引用密度 / 空话比例 / 与历史相似度"
 * 自评分低于阈值章节自动标红 + 浮窗提示 (Phase 3 接入)。
 */

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { AssetMetrics } from '@/types/api'

interface SelfAssessCardProps {
  metrics: AssetMetrics | null
  loading?: boolean
}

export function SelfAssessCard({ metrics, loading }: SelfAssessCardProps) {
  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex items-center gap-3 rounded-md border border-border-subtle bg-bg-card px-3 py-2">
        <span className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          自评卡
        </span>
        <Metric
          label="覆盖"
          value={metrics?.coverage}
          loading={loading}
          tooltip="生成内容覆盖候选 ValueSegment 的比例"
        />
        <Divider />
        <Metric
          label="引用"
          value={metrics?.citation_density}
          loading={loading}
          tooltip="段落内含 [N] 证据角标的密度"
        />
        <Divider />
        <Metric
          label="空话"
          value={metrics?.slop_score}
          loading={loading}
          tooltip="冗余 / 虚词比例 (越低越好)"
          isLowerBetter
        />
        <Divider />
        <Metric
          label="相似"
          value={metrics?.similarity}
          loading={loading}
          tooltip="与历史文档的内容相似度 (避免重复)"
          isLowerBetter
        />
      </div>
    </TooltipProvider>
  )
}

interface MetricProps {
  label: string
  value: number | undefined
  loading?: boolean
  tooltip: string
  isLowerBetter?: boolean
}

function Metric({ label, value, loading, tooltip, isLowerBetter }: MetricProps) {
  const pct = value === undefined ? null : Math.round(value * 100)
  const isWarn =
    pct !== null && (isLowerBetter ? pct > 20 : pct < 60)

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-baseline gap-1">
          <span className="font-ui text-caption text-text-muted">{label}</span>
          {loading ? (
            <span className="font-mono text-caption text-text-subtle">--</span>
          ) : (
            <span
              className={cn(
                'font-mono text-body-sm font-semibold tabular-nums',
                pct === null
                  ? 'text-text-subtle'
                  : isWarn
                    ? 'text-warning'
                    : 'text-text-primary',
              )}
            >
              {pct === null ? '—' : `${pct}%`}
            </span>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <p className="font-ui text-caption">{tooltip}</p>
      </TooltipContent>
    </Tooltip>
  )
}

function Divider() {
  return <span className="h-3 w-px bg-border-subtle" aria-hidden="true" />
}
