/**
 * useRegenerate · T08 章节重生成 mutation.
 *
 * POST /api/v1/assets/:asset_id/chapters/:chapter_id/regenerate
 *
 * onSuccess:
 *   - invalidate ['assets', assetId, 'chapters'] 让 ChapterBlock 拉新内容
 *   - invalidate ['assets', assetId, 'chapters', chapterId, 'evidence'] (重生成后引用可能变)
 *   - invalidate ['assets', assetId] (asset.updated_at 变)
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Chapter } from '@/types/api'

export interface RegenerateChapterPayload {
  assetId: string
  chapterId: string
  instruction: string
  model?: string
  provider?: string
}

async function postRegenerate(payload: RegenerateChapterPayload): Promise<Chapter> {
  const { data } = await api.post<Chapter>(
    `/assets/${payload.assetId}/chapters/${payload.chapterId}/regenerate`,
    {
      instruction: payload.instruction,
      model: payload.model,
      provider: payload.provider,
    },
  )
  return data
}

export function useRegenerate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: postRegenerate,
    onSuccess: (_chapter, vars) => {
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId, 'chapters'] })
      void qc.invalidateQueries({
        queryKey: ['assets', vars.assetId, 'chapters', vars.chapterId, 'evidence'],
      })
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId] })
    },
  })
}
