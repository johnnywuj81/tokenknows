/**
 * useChapterEvidence · GET /api/v1/assets/:id/chapters/:chapter_id/evidence
 *
 * T07: 抽屉一次性加载本章证据全集; 切换 evidence 仅 setActiveEvidenceId, 不重 query.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Evidence } from '@/types/api'

async function fetchChapterEvidence(
  assetId: string,
  chapterId: string,
): Promise<Evidence[]> {
  const { data } = await api.get<Evidence[]>(
    `/assets/${assetId}/chapters/${chapterId}/evidence`,
  )
  return data
}

export function useChapterEvidence(
  assetId: string | null | undefined,
  chapterId: string | null | undefined,
) {
  return useQuery({
    queryKey: ['assets', assetId, 'chapters', chapterId, 'evidence'],
    queryFn: () => fetchChapterEvidence(assetId as string, chapterId as string),
    enabled: Boolean(assetId && chapterId),
    // 抽屉打开期间不要 invalidate 让用户体验流畅
    staleTime: 60_000,
  })
}
