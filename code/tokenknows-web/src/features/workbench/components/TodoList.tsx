/**
 * TodoList · 右侧本周待办
 *
 * 排序: 按 due_at 升序;过期项目标红;无 due 排在最后。
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileCheck, Eye, Sparkles, Send, AlertTriangle, RotateCcw } from 'lucide-react'
import { EmptyState } from '@/components/shared/EmptyState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import type { TodoItem } from '@/types/api'
import { cn } from '@/lib/utils'

interface TodoListProps {
  todos: TodoItem[] | undefined
  isLoading: boolean
  error: unknown
  onRetry: () => void
  projectId: string | null | undefined
}

const TYPE_META: Record<TodoItem['type'], { icon: React.ComponentType<{ className?: string }>; label: string }> = {
  pending_review: { icon: FileCheck, label: '待审' },
  pending_redaction: { icon: Eye, label: '待脱敏' },
  pending_generate: { icon: Sparkles, label: '待生成' },
  pending_publish: { icon: Send, label: '待发布' },
  // T128 · 章节被 reviewer 退回, 作者需修订
  pending_revision: { icon: RotateCcw, label: '待修订' },
}

export function TodoList({ todos, isLoading, error, onRetry, projectId }: TodoListProps) {
  const navigate = useNavigate()
  // 捕获挂载时的 now,每 60s 重算 overdue (避免组件渲染期调 Date.now)
  const [now, setNow] = useState<number>(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <aside
      className="flex h-full flex-col gap-3 rounded-lg border border-border-subtle bg-bg-card p-4"
      aria-label="本周待办"
    >
      <header className="flex items-center justify-between">
        <h2 className="font-content text-h3 text-text-primary">本周待办</h2>
        {todos?.length ? (
          <span className="rounded bg-bg-warm px-1.5 py-0.5 font-ui text-micro font-medium text-text-secondary">
            {todos.length}
          </span>
        ) : null}
      </header>

      {error ? (
        <ErrorState
          variant="inline"
          title="待办加载失败"
          error={error}
          onRetry={onRetry}
        />
      ) : isLoading ? (
        <LoadingSkeleton variant="drawer" />
      ) : todos && todos.length > 0 ? (
        <ul className="space-y-2 overflow-auto">
          {sortTodos(todos).map((todo) => {
            const meta = TYPE_META[todo.type]
            const Icon = meta.icon
            const overdue = todo.due_at ? new Date(todo.due_at).getTime() < now : false
            return (
              <li key={todo.id}>
                <button
                  type="button"
                  onClick={() => {
                    if (!projectId) return
                    if (todo.asset_id) {
                      navigate(`/projects/${projectId}/documents/${todo.asset_id}`)
                    } else {
                      navigate(`/projects/${projectId}/documents`)
                    }
                  }}
                  className="group flex w-full items-start gap-2 rounded-md border border-border-subtle bg-bg-page p-2.5 text-left transition hover:border-border-medium hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                >
                  <Icon
                    className={cn(
                      'size-3.5 mt-0.5 shrink-0',
                      overdue ? 'text-danger' : 'text-text-muted',
                    )}
                  />
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <p className="line-clamp-2 font-ui text-body-sm text-text-primary">
                      {todo.title}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="font-ui text-micro text-text-subtle">
                        {meta.label}
                      </span>
                      {todo.due_at ? (
                        <span
                          className={cn(
                            'flex items-center gap-1 font-ui text-micro',
                            overdue ? 'text-danger' : 'text-text-subtle',
                          )}
                        >
                          {overdue ? <AlertTriangle className="size-2.5" /> : null}
                          {formatDue(todo.due_at, now)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <EmptyState
          icon={<FileCheck className="size-8 text-text-subtle" />}
          title="本周没有待办"
          description="新文档生成后会自动出现待审任务。"
        />
      )}
    </aside>
  )
}

function sortTodos(todos: TodoItem[]): TodoItem[] {
  return [...todos].sort((a, b) => {
    if (!a.due_at && !b.due_at) return 0
    if (!a.due_at) return 1
    if (!b.due_at) return -1
    return new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
  })
}

function formatDue(iso: string, now: number): string {
  const due = new Date(iso).getTime()
  const diffMs = due - now
  const DAY = 1000 * 60 * 60 * 24
  if (diffMs < 0) {
    const absDays = Math.floor(-diffMs / DAY)
    return absDays === 0 ? '今天已过期' : `逾期 ${absDays} 天`
  }
  const diffDay = Math.floor(diffMs / DAY)
  if (diffDay === 0) return '今天截止'
  if (diffDay === 1) return '明天截止'
  return `${diffDay} 天后`
}
