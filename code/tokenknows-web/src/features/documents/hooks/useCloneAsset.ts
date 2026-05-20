/**
 * useCloneAsset · POST /api/v1/assets/:assetId/clone
 *
 * 决策 (TaskTechDesign T05): "复制"是克隆 Asset 创建新草稿,
 * 不是复制链接(避免与"导出/分享"混淆)。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Asset } from '@/types/api'

interface ClonePayload {
  projectId: string
  assetId: string
}

async function cloneAssetRequest(payload: ClonePayload): Promise<Asset> {
  const { data } = await api.post<Asset>(`/assets/${payload.assetId}/clone`)
  return data
}

export function useCloneAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: cloneAssetRequest,
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({
        queryKey: ['projects', vars.projectId, 'assets'],
      })
    },
  })
}
