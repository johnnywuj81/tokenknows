/**
 * DatasourcesCard · 5 采集器实时状态
 *
 * 显示 5 个固定源, 即使 event_count=0 也保留行 (让用户知道"这个源可装")。
 * 颜色:
 *   - active   绿 · 24h 内有入库
 *   - stale    黄 · 7d 内有入库
 *   - cold     灰 · 7d 以前
 *   - inactive 灰白 · 历史 0 事件
 */

import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { DatasourceHealth, DatasourceHealthItem, DatasourceType } from '@/types/api'
import { cn } from '@/lib/utils'
import { formatRelative } from '@/lib/format'

interface DatasourcesCardProps {
  items: DatasourceHealthItem[] | undefined
  totalActive: number | undefined
  totalEventsAll: number | undefined
  isLoading: boolean
}

const SOURCE_LABEL: Record<DatasourceType, string> = {
  claude_code: 'Claude Code',
  claude_cowork: 'Claude Cowork',
  codex: 'Codex',
  github: 'GitHub',
  cursor: 'Cursor',
  vscode: 'VS Code',
  local_file: '本地文档',
}

// emoji 替代 icon, 减少额外依赖
const SOURCE_EMOJI: Record<DatasourceType, string> = {
  claude_code: '🤖',
  claude_cowork: '🤝',
  codex: '🧩',
  github: '🐙',
  cursor: '✏️',
  vscode: '🔵',
  local_file: '📝',
}

const HEALTH_DOT: Record<DatasourceHealth, string> = {
  active: 'bg-success',
  stale: 'bg-warning',
  cold: 'bg-text-muted',
  inactive: 'bg-border-strong',
}

const HEALTH_LABEL: Record<DatasourceHealth, string> = {
  active: '活跃 · 24h 内有数据',
  stale: '低活跃 · 7d 内有数据',
  cold: '已冷却 · 7d 以上无数据',
  inactive: '未启用 · 历史无数据',
}

const numberFmt = new Intl.NumberFormat('zh-CN')

export function DatasourcesCard({
  items,
  totalActive,
  totalEventsAll,
  isLoading,
}: DatasourcesCardProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <section
        className="rounded-lg border border-border-subtle bg-bg-card p-4"
        aria-label="数据采集器健康度"
      >
        <header className="mb-3 flex items-center justify-between gap-2">
          <h3 className="font-content text-h3 text-text-primary">数据源</h3>
          {!isLoading && totalActive !== undefined && totalEventsAll !== undefined ? (
            <span className="font-ui text-caption text-text-muted tabular-nums">
              {totalActive} 活跃 · {numberFmt.format(totalEventsAll)} 事件
            </span>
          ) : null}
        </header>

        {isLoading ? (
          <ul className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <li key={i}>
                <Skeleton className="h-9 w-full" />
              </li>
            ))}
          </ul>
        ) : (
          <ul className="space-y-1.5">
            {(items ?? []).map((item) => (
              <DatasourceRow key={item.source_type} item={item} />
            ))}
          </ul>
        )}
      </section>
    </TooltipProvider>
  )
}

function DatasourceRow({ item }: { item: DatasourceHealthItem }) {
  const label = SOURCE_LABEL[item.source_type] ?? item.source_type
  const emoji = SOURCE_EMOJI[item.source_type] ?? '●'
  const isInactive = item.health === 'inactive'
  return (
    <li>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-bg-page px-2.5 py-2',
              isInactive && 'opacity-60',
            )}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span aria-hidden className="text-sm">
                {emoji}
              </span>
              <span className="truncate font-ui text-caption text-text-primary">{label}</span>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="font-ui text-caption text-text-muted tabular-nums">
                {numberFmt.format(item.total_events)}
              </span>
              <span
                className={cn('size-2 shrink-0 rounded-full', HEALTH_DOT[item.health])}
                aria-label={HEALTH_LABEL[item.health]}
              />
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-xs">
          <div className="space-y-1 font-ui text-caption">
            <p>
              <strong>{label}</strong> · {HEALTH_LABEL[item.health]}
            </p>
            <p className="text-text-muted">
              历史 {numberFmt.format(item.total_events)} 事件 ·
              近 30 天 {numberFmt.format(item.event_count)} 事件
            </p>
            {item.last_ingested_at ? (
              <p className="text-text-muted">
                最近入库: {formatRelative(item.last_ingested_at)}
              </p>
            ) : null}
            {item.last_seen_at ? (
              <p className="text-text-muted">最近活动: {formatRelative(item.last_seen_at)}</p>
            ) : null}
          </div>
        </TooltipContent>
      </Tooltip>
    </li>
  )
}

