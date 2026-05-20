/**
 * ProjectStats · 项目数字卡(4 个指标)
 *
 * 决策: 千分位 + Tooltip 显示明细。
 */

import { Activity, FileCheck, Plug, Zap } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import type { Project, ProjectStats as Stats } from '@/types/api'
import { cn } from '@/lib/utils'

interface ProjectStatsProps {
  project: Project | undefined
  stats: Stats | undefined
  isLoading: boolean
}

const numberFmt = new Intl.NumberFormat('zh-CN')

export function ProjectStats({ project, stats, isLoading }: ProjectStatsProps) {
  const health = project?.health ?? 'healthy'
  const healthColor =
    health === 'healthy' ? 'bg-success' : health === 'degraded' ? 'bg-warning' : 'bg-danger'

  return (
    <TooltipProvider delayDuration={200}>
      <section
        className="rounded-lg border border-border-subtle bg-bg-card p-4"
        aria-label="项目概况"
      >
        <header className="mb-3 flex items-center justify-between">
          <div className="space-y-0.5 min-w-0">
            <h2 className="truncate font-content text-h3 text-text-primary">
              {project?.name ?? '加载中...'}
            </h2>
            {project?.description ? (
              <p className="line-clamp-1 text-caption text-text-muted">{project.description}</p>
            ) : null}
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                className={cn('flex size-2.5 shrink-0 rounded-full', healthColor)}
                aria-label={`项目健康: ${health}`}
              />
            </TooltipTrigger>
            <TooltipContent side="left">
              <p className="font-ui text-caption">
                项目健康度: <strong>{health === 'healthy' ? '正常' : health === 'degraded' ? '降级' : '故障'}</strong>
              </p>
            </TooltipContent>
          </Tooltip>
        </header>

        <ul className="grid grid-cols-2 gap-3">
          <StatItem
            icon={Activity}
            label="本周事件"
            value={stats?.events_this_week}
            isLoading={isLoading}
            tooltip="过去 7 天内被采集的研发事件总数(对话 / PR / commit / 文档等)"
          />
          <StatItem
            icon={FileCheck}
            label="待审文档"
            value={stats?.assets_pending_review}
            isLoading={isLoading}
            tooltip="处于 in_review 状态、等待 Reviewer 处理的资产数"
            valueColor={
              (stats?.assets_pending_review ?? 0) > 0 ? 'text-warning' : 'text-text-primary'
            }
          />
          <StatItem
            icon={Plug}
            label="数据源 (健康/总数)"
            value={
              stats
                ? `${numberFmt.format(stats.datasources_healthy)} / ${numberFmt.format(stats.datasources_total)}`
                : undefined
            }
            isLoading={isLoading}
            tooltip="健康 = 最近成功同步; 失败 = 鉴权过期 / API 错误"
          />
          <StatItem
            icon={Zap}
            label="最近活跃"
            value={project?.updated_at ? formatRelative(project.updated_at) : undefined}
            isLoading={isLoading}
            tooltip={project?.updated_at ?? ''}
          />
        </ul>
      </section>
    </TooltipProvider>
  )
}

interface StatItemProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number | undefined
  isLoading: boolean
  tooltip: string
  valueColor?: string
}

function StatItem({ icon: Icon, label, value, isLoading, tooltip, valueColor }: StatItemProps) {
  return (
    <li>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex flex-col gap-1 rounded-md border border-border-subtle bg-bg-page p-2.5">
            <div className="flex items-center gap-1.5 text-text-muted">
              <Icon className="size-3.5" />
              <span className="font-ui text-caption">{label}</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-7 w-16" />
            ) : (
              <span
                className={cn(
                  'font-content text-h2 leading-none tabular-nums',
                  valueColor ?? 'text-text-primary',
                )}
              >
                {typeof value === 'number' ? numberFmt.format(value) : (value ?? '—')}
              </span>
            )}
          </div>
        </TooltipTrigger>
        {tooltip ? (
          <TooltipContent side="bottom" className="max-w-xs">
            <p className="font-ui text-caption">{tooltip}</p>
          </TooltipContent>
        ) : null}
      </Tooltip>
    </li>
  )
}

function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 60 * 60) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 60 * 60 * 24) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}
