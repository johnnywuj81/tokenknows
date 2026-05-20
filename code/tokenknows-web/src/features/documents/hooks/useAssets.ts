/**
 * useAssets · GET /api/v1/projects/:id/assets (筛选 + cursor 分页)
 *
 * 决策 (TaskTechDesign T05):
 *   有 generating 文档时 polling 3s 自动刷新; 其余靠默认 staleTime。
 *
 * 实现说明: useInfiniteQuery 的 refetchInterval function 对 InfiniteData 不够稳定,
 *   改用 useEffect + setInterval 手动 refetch (更可读 + 避开 lib internal 边界)。
 */

import { useEffect } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Asset, AssetStatus, AssetType } from '@/types/api'

export interface AssetFilters {
  type?: AssetType
  status?: AssetStatus
}

interface AssetsResponse {
  data: Asset[]
  meta: { total: number; cursor: string | null; has_more: boolean }
}

async function fetchAssets(
  projectId: string,
  filters: AssetFilters,
  cursor: string | null,
): Promise<AssetsResponse> {
  const params: Record<string, string> = { limit: '20' }
  if (filters.type) params.type = filters.type
  if (filters.status) params.status = filters.status
  if (cursor) params.cursor = cursor
  const { data } = await api.get<AssetsResponse>(`/projects/${projectId}/assets`, {
    params,
  })
  return data
}

export function useAssets(
  projectId: string | null | undefined,
  filters: AssetFilters = {},
) {
  const query = useInfiniteQuery({
    queryKey: ['projects', projectId, 'assets', filters],
    queryFn: ({ pageParam }) => fetchAssets(projectId as string, filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.meta.cursor,
    enabled: Boolean(projectId),
  })

  // 有 generating 文档时手动 polling 3s
  const hasGenerating =
    query.data?.pages.some((p) => p.data.some((a) => a.status === 'generating')) ?? false

  useEffect(() => {
    if (!hasGenerating) return
    const id = setInterval(() => {
      query.refetch()
    }, 3_000)
    return () => clearInterval(id)
    // 故意只依赖 hasGenerating, refetch 引用稳定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasGenerating])

  return query
}
