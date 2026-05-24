/**
 * ProjectsListPage · 项目列表
 *
 * 入口: ProjectSwitcher 下拉里"查看全部" (项目数 > 5 时出现).
 *
 * 设计:
 *   - 顶部: 标题 "项目 (N)" + "+ 新建项目"
 *   - 主区: 卡片 grid (响应式 1/2/3 列)
 *   - 卡片: 名称 + 描述 + health dot + role tag + mini stats + 相对时间
 *   - 当前项目卡片左上角带 ✓ 标识
 *   - 点击卡 → setCurrent + navigate(/projects/:id)
 */

import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Plus, Check, Folder, Activity, AlertCircle, FileText, Plug } from 'lucide-react'
import { useProjects } from '@/features/workbench/hooks/useProjects'
import { useProjectStore } from '@/stores/projectStore'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { Skeleton } from '@/components/ui/skeleton'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Project } from '@/types/api'

const HEALTH_DOT: Record<NonNullable<Project['health']>, string> = {
  healthy: 'bg-success',
  degraded: 'bg-warning',
  down: 'bg-error',
}

const HEALTH_LABEL: Record<NonNullable<Project['health']>, string> = {
  healthy: '健康',
  degraded: '降级',
  down: '宕机',
}

export default function ProjectsListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentProjectId = useProjectStore((s) => s.currentProjectId)
  const setCurrent = useProjectStore((s) => s.setCurrent)
  const { data: projects, isLoading, error, refetch } = useProjects()

  function handleOpen(projectId: string) {
    if (projectId !== currentProjectId) {
      queryClient.cancelQueries({ queryKey: ['projects', currentProjectId] })
      setCurrent(projectId)
    }
    navigate(`/projects/${projectId}`)
  }

  if (isLoading) {
    return <LoadingSkeleton variant="list" />
  }

  if (error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="项目列表加载失败"
        error={error}
        onRetry={() => refetch()}
      />
    )
  }

  const list = projects ?? []

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-content text-h2 text-text-primary">项目</h1>
          <p className="mt-1 font-ui text-caption text-text-muted">
            共 {list.length} 个项目 · 当前: {projects?.find((p) => p.id === currentProjectId)?.name ?? '未选择'}
          </p>
        </div>
        <Link
          to="/projects/new"
          className="inline-flex items-center gap-1.5 rounded-md bg-accent-primary px-3 py-1.5 font-ui text-body-sm text-inverse-text transition hover:bg-accent-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          <Plus className="size-3.5" />
          新建项目
        </Link>
      </header>

      {list.length === 0 ? (
        <EmptyProjects />
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((p) => (
            <li key={p.id}>
              <ProjectCard
                project={p}
                isCurrent={p.id === currentProjectId}
                onOpen={() => handleOpen(p.id)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface ProjectCardProps {
  project: Project
  isCurrent: boolean
  onOpen: () => void
}

function ProjectCard({ project, isCurrent, onOpen }: ProjectCardProps) {
  const health = project.health ?? 'healthy'
  const stats = project.stats

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'group relative flex h-full w-full flex-col gap-3 rounded-lg border bg-bg-card p-4 text-left transition',
        'hover:border-accent-primary hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary',
        isCurrent
          ? 'border-accent-primary ring-1 ring-accent-primary'
          : 'border-border-subtle',
      )}
      aria-label={`打开项目 ${project.name}${isCurrent ? ' (当前)' : ''}`}
    >
      {isCurrent ? (
        <span
          className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-sm bg-accent-primary-light px-1.5 py-0.5 font-ui text-micro font-medium text-accent-primary-dark"
          title="当前活动项目"
        >
          <Check className="size-3" />
          当前
        </span>
      ) : null}

      <header className="flex items-start gap-2 pr-12">
        <Folder className="mt-0.5 size-4 shrink-0 text-text-muted group-hover:text-accent-primary" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-content text-h3 text-text-primary">
            {project.name}
          </h3>
          <p className="mt-0.5 truncate font-mono text-caption text-text-subtle">
            {project.id}
          </p>
        </div>
      </header>

      {project.description ? (
        <p className="line-clamp-2 font-ui text-body-sm text-text-secondary">
          {project.description}
        </p>
      ) : (
        <p className="font-ui text-body-sm text-text-muted italic">无描述</p>
      )}

      <div className="flex items-center gap-2 font-ui text-caption">
        <span
          className={cn('inline-block size-2 rounded-full', HEALTH_DOT[health])}
          title={HEALTH_LABEL[health]}
          aria-hidden
        />
        <span className="text-text-muted">{HEALTH_LABEL[health]}</span>
        {project.role ? (
          <>
            <span className="text-border-medium">·</span>
            <span className="rounded-sm bg-bg-warm px-1.5 py-0.5 font-medium text-text-secondary">
              {project.role}
            </span>
          </>
        ) : null}
      </div>

      {stats ? (
        <dl className="mt-auto grid grid-cols-3 gap-2 border-t border-border-subtle pt-3 font-ui text-caption">
          <Stat
            icon={Activity}
            label="本周事件"
            value={stats.events_this_week}
          />
          <Stat
            icon={FileText}
            label="待审批"
            value={stats.assets_pending_review}
            warn={stats.assets_pending_review > 0}
          />
          <Stat
            icon={Plug}
            label="数据源"
            value={`${stats.datasources_healthy}/${stats.datasources_total}`}
            warn={stats.datasources_healthy < stats.datasources_total}
          />
        </dl>
      ) : (
        <Skeleton className="mt-auto h-10 w-full" />
      )}

      <footer className="font-ui text-micro text-text-subtle">
        创建于 {formatRelative(project.created_at)}
      </footer>
    </button>
  )
}

interface StatProps {
  icon: typeof Activity
  label: string
  value: number | string
  warn?: boolean
}

function Stat({ icon: Icon, label, value, warn }: StatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="flex items-center gap-1 text-text-muted">
        <Icon className="size-3" />
        {label}
      </dt>
      <dd
        className={cn(
          'font-medium tabular-nums',
          warn ? 'text-warning-dark' : 'text-text-primary',
        )}
      >
        {value}
      </dd>
    </div>
  )
}

function EmptyProjects() {
  return (
    <div className="rounded-lg border border-dashed border-border-medium bg-bg-card p-12 text-center">
      <AlertCircle className="mx-auto mb-3 size-8 text-text-muted" />
      <h2 className="font-content text-h3 text-text-primary">还没有项目</h2>
      <p className="mt-1 font-ui text-body-sm text-text-muted">
        新建第一个项目开始把研发过程汇聚成知识资产。
      </p>
      <Link
        to="/projects/new"
        className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-accent-primary px-3 py-1.5 font-ui text-body-sm text-inverse-text hover:bg-accent-primary-dark"
      >
        <Plus className="size-3.5" />
        新建项目
      </Link>
    </div>
  )
}
