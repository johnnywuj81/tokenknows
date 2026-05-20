/**
 * useEventStream · 工作台事件流(useInfiniteQuery + 30s polling)
 *
 * 设计依据:
 *   - TaskTechDesign T03 关键决策: "MVP 走 30s polling, 不上 SSE"
 *   - SharedFoundations §5.4: SSE 替换点留在 W4D17
 *
 * SSE 替换点: 改为订阅 EventSource('/api/v1/ws/projects/:id/events')
 *   收到新事件时 queryClient.setQueryData(['projects', id, 'events', filters], ...)
 *   并停用 refetchInterval。
 */

import { useInfiniteQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Event, EventSourceType } from '@/types/api'

export interface EventStreamFilters {
  source_type?: EventSourceType
  author?: string
}

interface EventsResponse {
  data: Event[]
  meta: { total: number; cursor: string | null; has_more: boolean }
}

async function fetchEvents(
  projectId: string,
  filters: EventStreamFilters,
  cursor: string | null,
): Promise<EventsResponse> {
  const params: Record<string, string> = { limit: '20' }
  if (filters.source_type) params.source_type = filters.source_type
  if (filters.author) params.author = filters.author
  if (cursor) params.cursor = cursor
  const { data } = await api.get<EventsResponse>(`/projects/${projectId}/events`, { params })
  return data
}

export function useEventStream(
  projectId: string | null | undefined,
  filters: EventStreamFilters = {},
) {
  return useInfiniteQuery({
    queryKey: ['projects', projectId, 'events', filters],
    queryFn: ({ pageParam }) => fetchEvents(projectId as string, filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.meta.cursor,
    enabled: Boolean(projectId),
    // SSE 替换点 START
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    // SSE 替换点 END
  })
}
