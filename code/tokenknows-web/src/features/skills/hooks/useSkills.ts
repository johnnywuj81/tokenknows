/**
 * useSkills · TanStack Query hooks for v0.2 Skill API
 *
 * 端点对应:
 *   GET    /projects/:id/skills          → useSkills
 *   GET    /skills/:id                   → useSkill
 *   POST   /projects/:id/skills/distill  → useDistillSkill
 *   PATCH  /skills/:id                   → useUpdateSkill
 *   POST   /skills/:id/lock|unlock       → useLockSkill / useUnlockSkill
 *   POST   /skills/:id/evolve            → useEvolveSkill
 *   DELETE /skills/:id                   → useDeleteSkill
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  ConsentRejectRequest,
  ConsentRejectResponse,
  ConsentSignRequest,
  ConsentSignResponse,
  Skill,
  SkillDistillRequest,
  SkillStatus,
  SkillUpdateRequest,
} from '@/types/api'

const skillKey = {
  list: (projectId: string, status?: SkillStatus) =>
    ['skills', projectId, status ?? 'all'] as const,
  detail: (skillId: string) => ['skills', 'detail', skillId] as const,
}

export function useSkills(projectId: string, status?: SkillStatus) {
  return useQuery({
    queryKey: skillKey.list(projectId, status),
    queryFn: async () => {
      const search = status ? `?status=${status}` : ''
      const res = await api.get<Skill[]>(`/projects/${projectId}/skills${search}`)
      return res.data
    },
    enabled: Boolean(projectId),
  })
}

export function useSkill(skillId: string | null) {
  return useQuery({
    queryKey: skillKey.detail(skillId ?? ''),
    queryFn: async () => {
      const res = await api.get<Skill>(`/skills/${skillId}`)
      return res.data
    },
    enabled: Boolean(skillId),
  })
}

export function useDistillSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SkillDistillRequest) => {
      const res = await api.post<Skill>(
        `/projects/${projectId}/skills/distill`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
    },
  })
}

export function useUpdateSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      skillId,
      body,
    }: { skillId: string; body: SkillUpdateRequest }) => {
      const res = await api.patch<Skill>(`/skills/${skillId}`, body)
      return res.data
    },
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
      qc.invalidateQueries({ queryKey: skillKey.detail(updated.id) })
    },
  })
}

export function useLockSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      const res = await api.post<Skill>(`/skills/${skillId}/lock`, {})
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
    },
  })
}

export function useUnlockSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      const res = await api.post<Skill>(`/skills/${skillId}/unlock`, {})
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
    },
  })
}

export function useEvolveSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      const res = await api.post<Skill>(`/skills/${skillId}/evolve`, {})
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
    },
  })
}

export function useDeleteSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (skillId: string) => {
      await api.delete(`/skills/${skillId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
    },
  })
}

// ─── v0.5.1 · Consent (T50) ──────────────────────────────────────

export function useSignConsent(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      skillId,
      body,
    }: { skillId: string; body: ConsentSignRequest }) => {
      const res = await api.post<ConsentSignResponse>(
        `/skills/${skillId}/consent/sign`,
        body,
      )
      return res.data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
      qc.invalidateQueries({ queryKey: skillKey.detail(data.skill_id) })
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useRejectConsent(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      skillId,
      body,
    }: { skillId: string; body: ConsentRejectRequest }) => {
      const res = await api.post<ConsentRejectResponse>(
        `/skills/${skillId}/consent/reject`,
        body,
      )
      return res.data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['skills', projectId] })
      qc.invalidateQueries({ queryKey: skillKey.detail(data.skill_id) })
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}
