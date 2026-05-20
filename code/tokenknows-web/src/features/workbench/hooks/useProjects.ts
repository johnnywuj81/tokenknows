/**
 * useProjects · GET /api/v1/projects
 *
 * 用于工作台顶栏的 ProjectSwitcher + 空态判断。
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Project } from '@/types/api'

async function fetchProjects(): Promise<Project[]> {
  const { data } = await api.get<Project[]>('/projects')
  return data
}

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })
}
