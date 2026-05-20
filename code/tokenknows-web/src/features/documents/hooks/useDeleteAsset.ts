/**
 * useDeleteAsset · DELETE /api/v1/assets/:assetId
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface DeletePayload {
  projectId: string
  assetId: string
}

async function deleteAssetRequest(payload: DeletePayload): Promise<void> {
  await api.delete(`/assets/${payload.assetId}`)
}

export function useDeleteAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteAssetRequest,
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({
        queryKey: ['projects', vars.projectId, 'assets'],
      })
    },
  })
}
