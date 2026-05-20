/**
 * useProject · GET /api/v1/projects/:id (单项目详情)
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Project } from '@/types/api'

async function fetchProject(id: string): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${id}`)
  return data
}

export function useProject(id: string | null | undefined) {
  return useQuery({
    queryKey: ['projects', id],
    queryFn: () => fetchProject(id as string),
    enabled: Boolean(id),
  })
}
