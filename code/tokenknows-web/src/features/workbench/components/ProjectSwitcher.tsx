/**
 * ProjectSwitcher · 顶栏项目切换 dropdown
 *
 * 决策依据 (TaskTechDesign T03):
 *   不要全屏跳转切项目 — 下拉菜单选 + URL 更新即可。
 *
 * 显示最近 5 个项目 + "查看全部" + "+ 新建项目"。
 */

import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, Plus, Folder } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useProjectStore } from '@/stores/projectStore'
import { useProjects } from '../hooks/useProjects'
import { cn } from '@/lib/utils'

const RECENT_LIMIT = 5

export function ProjectSwitcher() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentProjectId = useProjectStore((s) => s.currentProjectId)
  const setCurrent = useProjectStore((s) => s.setCurrent)
  const { data: projects } = useProjects()

  const current = projects?.find((p) => p.id === currentProjectId)

  const handleSelect = (projectId: string) => {
    if (projectId === currentProjectId) return
    // 切换前取消旧项目 in-flight 查询
    queryClient.cancelQueries({ queryKey: ['projects', currentProjectId] })
    setCurrent(projectId)
    navigate(`/projects/${projectId}`)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md border border-border-subtle bg-bg-card px-2.5 py-1 font-ui text-body-sm text-text-secondary transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          <Folder className="size-3.5 text-text-muted" />
          <span className="max-w-[160px] truncate">
            {current?.name ?? (currentProjectId ? '加载中...' : '选择项目')}
          </span>
          <ChevronDown className="size-3.5 text-text-muted" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          最近项目
        </DropdownMenuLabel>
        {projects?.slice(0, RECENT_LIMIT).map((p) => {
          const active = p.id === currentProjectId
          return (
            <DropdownMenuItem
              key={p.id}
              onSelect={() => handleSelect(p.id)}
              className={cn(
                'flex items-start gap-2 font-ui',
                active && 'bg-accent-primary-light text-accent-primary-dark',
              )}
            >
              <div className="flex-1 min-w-0">
                <p className="truncate text-body-sm font-medium">{p.name}</p>
                <p className="font-mono text-caption text-text-subtle">{p.id.slice(0, 16)}</p>
              </div>
              {active ? <Check className="size-3.5 shrink-0 mt-0.5" /> : null}
            </DropdownMenuItem>
          )
        })}
        {(projects?.length ?? 0) > RECENT_LIMIT ? (
          <DropdownMenuItem
            onSelect={() => navigate('/projects')}
            className="font-ui text-caption text-text-muted"
          >
            查看全部 ({projects?.length})
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => navigate('/projects/new')}
          className="font-ui text-body-sm text-accent-primary-dark"
        >
          <Plus className="size-3.5" />
          新建项目
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
