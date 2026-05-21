/**
 * EventStream · 中间栏实时事件流
 *
 * 设计依据 (任务包 T03 §8):
 *   - 按"今天/昨天/周三 12 月 X 日"分组
 *   - polling 30s 自动刷新(useEventStream 内置)
 *   - "加载更早"按钮触发 fetchNextPage
 *   - 切项目时取消 in-flight (useEventStream enabled 控制)
 */

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, MoreHorizontal, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/EmptyState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useEventStream } from '../hooks/useEventStream'
import type { Event, EventSourceType } from '@/types/api'
import { EventCard } from './EventCard'
import { EventFilter } from './EventFilter'

interface EventStreamProps {
  projectId: string | null | undefined
}

export function EventStream({ projectId }: EventStreamProps) {
  const navigate = useNavigate()
  const [sourceType, setSourceType] = useState<EventSourceType | null>(null)
  const query = useEventStream(projectId, sourceType ? { source_type: sourceType } : {})
  const openEventDrawer = useDocumentUiStore((s) => s.openEventDrawer)

  const allEvents = useMemo(
    () => (query.data?.pages ?? []).flatMap((p) => p.data),
    [query.data],
  )
  const grouped = useMemo(() => groupByDay(allEvents), [allEvents])

  return (
    <section
      className="flex h-full flex-col gap-3 rounded-lg border border-border-subtle bg-bg-card p-4"
      aria-label="实时事件流"
    >
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="font-content text-h3 text-text-primary">实时事件流</h2>
          {query.isFetching && !query.isLoading ? (
            <RefreshCw className="size-3.5 animate-spin text-text-muted" aria-label="刷新中" />
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <EventFilter sourceType={sourceType} onChange={setSourceType} />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => query.refetch()}
            className="font-ui text-caption"
            aria-label="立即刷新"
          >
            <MoreHorizontal className="size-3.5" />
          </Button>
        </div>
      </header>

      <p className="font-ui text-caption text-text-subtle">
        polling 每 30 秒自动刷新 · <span className="font-mono">SSE 替换点 W4D17</span>
      </p>

      {query.error ? (
        <ErrorState
          variant="inline"
          title="事件流加载失败"
          error={query.error}
          onRetry={() => query.refetch()}
        />
      ) : query.isLoading ? (
        <LoadingSkeleton variant="drawer" />
      ) : allEvents.length === 0 ? (
        <EmptyState
          title={sourceType ? '该来源近期没有事件' : '尚无事件流入'}
          description={
            sourceType
              ? '尝试切换其它来源或检查该数据源是否健康。'
              : '插件采集会自动写入事件流。检查是否已生成连接 token 并安装插件。'
          }
          action={
            !sourceType && projectId
              ? {
                  label: '前往项目设置',
                  onClick: () => navigate(`/projects/${projectId}/settings`),
                }
              : undefined
          }
        />
      ) : (
        <div className="flex-1 space-y-4 overflow-auto pr-1">
          {grouped.map(({ label, items }) => (
            <section key={label} className="space-y-2">
              <h3 className="sticky top-0 z-10 bg-bg-card/95 backdrop-blur py-1 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
                {label} <span className="ml-1 text-text-subtle">· {items.length}</span>
              </h3>
              <ul className="space-y-1.5">
                {items.map((e) => (
                  <li key={e.id}>
                    <EventCard event={e} onClick={() => handleClick(e)} />
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {query.hasNextPage ? (
            <div className="flex justify-center pb-2">
              <Button
                variant="outline"
                onClick={() => query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
                className="font-ui text-caption"
              >
                {query.isFetchingNextPage ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    加载中
                  </>
                ) : (
                  '加载更早'
                )}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  )

  function handleClick(e: Event) {
    // T04 · 打开事件详情抽屉 (store-based, 与 T07 EvidenceDrawer 一致)
    openEventDrawer(e.id)
  }
}

interface Group {
  label: string
  items: Event[]
}

function groupByDay(events: Event[]): Group[] {
  const today = startOfDay(new Date())
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
  const groups = new Map<string, Event[]>()

  for (const e of events) {
    const d = startOfDay(new Date(e.occurred_at))
    const label =
      d.getTime() === today.getTime()
        ? '今天'
        : d.getTime() === yesterday.getTime()
          ? '昨天'
          : d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })
    const arr = groups.get(label)
    if (arr) arr.push(e)
    else groups.set(label, [e])
  }
  return [...groups.entries()].map(([label, items]) => ({ label, items }))
}

function startOfDay(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}
