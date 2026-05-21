/**
 * useReviewMutations · T09 章节审批 mutations.
 *
 * - useApproveChapter(): POST /assets/:id/chapters/:cid/approve
 * - useRejectChapter():  POST /assets/:id/chapters/:cid/reject body {reason}
 * - useSubmitAsset():    POST /assets/:id/submit (作者提交审批)
 *
 * 全部在成功后 invalidate chapters + asset queries.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'

interface ChapterMutationVars {
  assetId: string
  chapterId: string
}

interface RejectVars extends ChapterMutationVars {
  reason: string
}

function invalidateAsset(qc: ReturnType<typeof useQueryClient>, assetId: string) {
  void qc.invalidateQueries({ queryKey: ['assets', assetId] })
  void qc.invalidateQueries({ queryKey: ['assets', assetId, 'chapters'] })
}

export function useApproveChapter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: ChapterMutationVars) => {
      const { data } = await api.post<Chapter>(
        `/assets/${vars.assetId}/chapters/${vars.chapterId}/approve`,
      )
      return data
    },
    onSuccess: (_data, vars) => invalidateAsset(qc, vars.assetId),
  })
}

export function useRejectChapter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: RejectVars) => {
      const { data } = await api.post<Chapter>(
        `/assets/${vars.assetId}/chapters/${vars.chapterId}/reject`,
        { reason: vars.reason },
      )
      return data
    },
    onSuccess: (_data, vars) => invalidateAsset(qc, vars.assetId),
  })
}

export function useSubmitAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (assetId: string) => {
      const { data } = await api.post<Asset>(`/assets/${assetId}/submit`)
      return data
    },
    onSuccess: (_data, assetId) => invalidateAsset(qc, assetId),
  })
}
