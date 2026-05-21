/**
 * useEvent · GET /api/v1/events/:id
 *
 * T04 事件详情抽屉打开时调用. staleTime 30s 让多次点击同一 event 不重复 fetch.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Event } from '@/types/api'

async function fetchEvent(id: string): Promise<Event> {
  const { data } = await api.get<Event>(`/events/${id}`)
  return data
}

export function useEvent(eventId: string | null | undefined) {
  return useQuery({
    queryKey: ['events', eventId],
    queryFn: () => fetchEvent(eventId as string),
    enabled: Boolean(eventId),
    staleTime: 30_000,
  })
}
