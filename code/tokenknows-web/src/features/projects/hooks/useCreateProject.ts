/**
 * useCreateProject · POST /api/v1/projects → 返回 Project
 *
 * 注意: invalidate ['projects'] 让首页列表能看到新建项目。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Project } from '@/types/api'

interface CreateProjectPayload {
  name: string
  description?: string
}

async function createProjectRequest(payload: CreateProjectPayload): Promise<Project> {
  const { data } = await api.post<Project>('/projects', payload)
  return data
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createProjectRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
