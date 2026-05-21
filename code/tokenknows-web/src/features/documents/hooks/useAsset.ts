/**
 * useAsset · GET /api/v1/assets/:id
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Asset } from '@/types/api'

async function fetchAsset(id: string): Promise<Asset> {
  const { data } = await api.get<Asset>(`/assets/${id}`)
  return data
}

export function useAsset(id: string | null | undefined) {
  return useQuery({
    queryKey: ['assets', id],
    queryFn: () => fetchAsset(id as string),
    enabled: Boolean(id),
  })
}
