/**
 * useDatasourceHealth · GET /api/v1/projects/:id/datasources/health
 *
 * 5 个采集器的实时状态。30s 刷一次, 比 stats 更频繁——
 * 用户安完插件想立刻看到事件涌入。
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { DatasourceHealthResponse } from '@/types/api'

async function fetchDatasourceHealth(
  projectId: string,
  windowDays = 30,
): Promise<DatasourceHealthResponse> {
  const { data } = await api.get<DatasourceHealthResponse>(
    `/projects/${projectId}/datasources/health`,
    { params: { window_days: windowDays } },
  )
  return data
}

export function useDatasourceHealth(projectId: string | null | undefined, windowDays = 30) {
  return useQuery({
    queryKey: ['projects', projectId, 'datasources-health', windowDays],
    queryFn: () => fetchDatasourceHealth(projectId as string, windowDays),
    enabled: Boolean(projectId),
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  })
}
