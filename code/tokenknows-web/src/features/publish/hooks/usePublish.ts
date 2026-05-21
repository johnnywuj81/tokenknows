/**
 * usePublish · T11/T12 发布 mutation + query
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { PublishRecord, PublishMode, PublishDestination } from '@/types/api'

interface PublishVars {
  assetId: string
  destinations: PublishDestination[]
  publishMode: PublishMode
  visibility?: 'team' | 'public' | null
}

export function usePublishAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: PublishVars): Promise<PublishRecord[]> => {
      const { data } = await api.post<PublishRecord[]>(
        `/assets/${vars.assetId}/publish`,
        {
          destinations: vars.destinations,
          publish_mode: vars.publishMode,
          visibility: vars.visibility,
        },
      )
      return data
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId] })
      void qc.invalidateQueries({
        queryKey: ['assets', vars.assetId, 'publish-records'],
      })
    },
  })
}

export function usePublishRecord(recordId: string | null | undefined) {
  return useQuery({
    queryKey: ['publish-records', recordId],
    queryFn: async (): Promise<PublishRecord> => {
      const { data } = await api.get<PublishRecord>(
        `/publish-records/${recordId}`,
      )
      return data
    },
    enabled: Boolean(recordId),
  })
}

export function useAssetPublishRecords(assetId: string | null | undefined) {
  return useQuery({
    queryKey: ['assets', assetId, 'publish-records'],
    queryFn: async (): Promise<PublishRecord[]> => {
      const { data } = await api.get<PublishRecord[]>(
        `/assets/${assetId}/publish-records`,
      )
      return data
    },
    enabled: Boolean(assetId),
  })
}
