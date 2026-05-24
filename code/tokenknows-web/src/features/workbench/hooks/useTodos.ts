/**
 * useTodos · GET /api/v1/projects/:id/todos
 *
 * T134 · 红点 badge 依赖此查询有"baseline → 新增"对比能力.
 * T135 · 加 refetchInterval=60s 兜底:
 *   主推送路径是 T129 SSE asset_chapter_rejected → invalidate ['projects'].
 *   SSE 可能因 proxy 掐线 / 离线 / 用户没登录 而暂时无效 → 60s polling 保证
 *   即便 SSE 死了, 作者最多 60s 内还是看得到新 todo.
 *   refetchIntervalInBackground=false: tab 不在前台时不浪费请求,
 *   tab 回前台 TanStack Query 自带 refetchOnWindowFocus 会立刻补一次.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { TodoItem } from '@/types/api'

const TODOS_POLL_INTERVAL_MS = 60_000

async function fetchTodos(id: string): Promise<TodoItem[]> {
  const { data } = await api.get<TodoItem[]>(`/projects/${id}/todos`)
  return data
}

export function useTodos(id: string | null | undefined) {
  return useQuery({
    queryKey: ['projects', id, 'todos'],
    queryFn: () => fetchTodos(id as string),
    enabled: Boolean(id),
    refetchInterval: TODOS_POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  })
}
