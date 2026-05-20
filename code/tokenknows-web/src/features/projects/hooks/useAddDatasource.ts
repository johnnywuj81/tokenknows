/**
 * useAddDatasource · POST /api/v1/projects/:id/datasources/:type
 *
 * 接入类型:
 *   - claude_code / cursor / vscode → 返回 connection_token
 *   - github → 验 PAT(以 ghp_ 开头) + repos
 *   - local_file → 不在向导内创建(走文件上传)
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Datasource, DatasourceType } from '@/types/api'

interface AddDatasourcePayload {
  projectId: string
  type: DatasourceType
  body?: {
    name?: string
    pat?: string
    repos?: string[]
  }
}

async function addDatasourceRequest({
  projectId,
  type,
  body,
}: AddDatasourcePayload): Promise<Datasource> {
  const { data } = await api.post<Datasource>(
    `/projects/${projectId}/datasources/${type}`,
    body ?? {},
  )
  return data
}

export function useAddDatasource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: addDatasourceRequest,
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({
        queryKey: ['projects', vars.projectId, 'datasources'],
      })
    },
  })
}
