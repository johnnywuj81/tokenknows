/**
 * useProjectStats · GET /api/v1/projects/:id/stats (60s staleTime)
 *
 * 数字卡用。比项目详情更新频次高。
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProjectStats } from '@/types/api'

async function fetchProjectStats(id: string): Promise<ProjectStats> {
  const { data } = await api.get<ProjectStats>(`/projects/${id}/stats`)
  return data
}

export function useProjectStats(id: string | null | undefined) {
  return useQuery({
    queryKey: ['projects', id, 'stats'],
    queryFn: () => fetchProjectStats(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  })
}
