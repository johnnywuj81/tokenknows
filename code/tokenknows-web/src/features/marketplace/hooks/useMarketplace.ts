/**
 * useMarketplace · v1.0.0 T70 hooks.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  MarketplaceListResponse,
  Skill,
  SkillImportRequest,
  SkillPublishResponse,
} from '@/types/api'

const marketplaceKey = {
  list: (q: string, minTrust: number) =>
    ['marketplace', 'list', q, minTrust] as const,
}

export function useMarketplaceSkills(q = '', minTrust = 0) {
  return useQuery({
    queryKey: marketplaceKey.list(q, minTrust),
    queryFn: async (): Promise<MarketplaceListResponse> => {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (minTrust > 0) params.set('min_trust', String(minTrust))
      const url = `/marketplace/skills${
        params.toString() ? '?' + params.toString() : ''
      }`
      const res = await api.get<MarketplaceListResponse>(url)
      return res.data
    },
  })
}

export function usePublishSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      const res = await api.post<SkillPublishResponse>(
        `/skills/${skillId}/publish`,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
      qc.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useUnpublishSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      const res = await api.post<SkillPublishResponse>(
        `/skills/${skillId}/unpublish`,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
      qc.invalidateQueries({ queryKey: ['marketplace'] })
    },
  })
}

export function useImportSkill(targetProjectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SkillImportRequest) => {
      const res = await api.post<Skill>(
        `/projects/${targetProjectId}/skills/import`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', targetProjectId] })
    },
  })
}
