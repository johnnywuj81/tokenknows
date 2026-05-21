/**
 * useChapters · GET /api/v1/assets/:id/chapters
 *
 * 注意: 后端 Chapter 类型与前端 types/api.ts 镜像 (TDD §5.3).
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Chapter } from '@/types/api'

async function fetchChapters(assetId: string): Promise<Chapter[]> {
  const { data } = await api.get<Chapter[]>(`/assets/${assetId}/chapters`)
  return data
}

export function useChapters(assetId: string | null | undefined) {
  return useQuery({
    queryKey: ['assets', assetId, 'chapters'],
    queryFn: () => fetchChapters(assetId as string),
    enabled: Boolean(assetId),
  })
}
