/**
 * TodoList · 右侧本周待办
 *
 * 排序: 按 due_at 升序;过期项目标红;无 due 排在最后。
 *
 * T134: SSE 推来的新 todo (asset_chapter_rejected 等) 第一次出现时打红点;
 * 点击该 todo 或"全部已读"按钮后红点消失. Baseline 在挂载时取首批 todo IDs,
 * 不持久化 (页面刷新 = 新 baseline, 简单足够 MVP).
 */

import { useEffect, useMemo, useState } from 'react'
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

  // T134 · "已读"集合: 挂载时首批 todos 自动入集, SSE/polling 后续新增 todos
  // 不在集合内 → 红点. seenIds=null 表示还没挂载/首批未到, 此时不打任何红点
  // (避免初始 loading 后所有 todos 都被当成"新").
  const [seenIds, setSeenIds] = useState<Set<string> | null>(null)
  useEffect(() => {
    // 首批 todos 到达时初始化 baseline (空数组也算"到了", 后续才能识别新增).
    // setState-in-effect 是有意为之: 必须等异步 todos 到位才能取 baseline,
    // 没有别的 React 钩子能在不阻塞渲染的同时做这件事; 一次性条件守卫
    // (seenIds === null) 保证最多触发一次额外渲染.
    if (seenIds === null && todos !== undefined) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSeenIds(new Set(todos.map((t) => t.id)))
    }
  }, [todos, seenIds])

  const newCount = useMemo(() => {
    if (!todos || seenIds === null) return 0
    return todos.filter((t) => !seenIds.has(t.id)).length
  }, [todos, seenIds])

  function markSeen(id: string): void {
    setSeenIds((prev) => {
      const next = new Set(prev ?? [])
      next.add(id)
      return next
    })
  }

  function markAllSeen(): void {
    setSeenIds(new Set(todos?.map((t) => t.id) ?? []))
  }

  return (
    <aside
      className="flex h-full flex-col gap-3 rounded-lg border border-border-subtle bg-bg-card p-4"
      aria-label="本周待办"
    >
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="font-content text-h3 text-text-primary">本周待办</h2>
          {/* T134 · 新到红点徽章, 显示新 todo 数量 */}
          {newCount > 0 ? (
            <span
              data-testid="todo-new-count"
              className="rounded-full bg-danger px-1.5 py-0.5 font-ui text-micro font-medium text-white"
              title={`${newCount} 条新待办`}
            >
              {newCount} 新
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {/* T134 · 全部已读 (只在有新待办时显示) */}
          {newCount > 0 ? (
            <button
              type="button"
              data-testid="todo-mark-all-seen"
              onClick={markAllSeen}
              className="font-ui text-micro text-text-muted hover:text-text-primary"
            >
              全部已读
            </button>
          ) : null}
          {todos?.length ? (
            <span className="rounded bg-bg-warm px-1.5 py-0.5 font-ui text-micro font-medium text-text-secondary">
              {todos.length}
            </span>
          ) : null}
        </div>
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
            // T134 · 该 todo 是不是新到的 (不在 seenIds 集合内)
            const isNew = seenIds !== null && !seenIds.has(todo.id)
            return (
              <li key={todo.id} className="relative">
                {/* T134 · 红点角标, 绝对定位左上角避免干扰 hover/focus */}
                {isNew ? (
                  <span
                    data-testid={`todo-new-dot-${todo.id}`}
                    aria-label="新待办"
                    className="absolute top-1.5 left-1.5 z-10 size-1.5 rounded-full bg-danger ring-2 ring-bg-card"
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    if (isNew) markSeen(todo.id)
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
