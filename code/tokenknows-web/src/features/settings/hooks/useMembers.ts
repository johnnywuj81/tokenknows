/**
 * useMembers · v0.9.0 T67 TanStack Query hooks for project members.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  AddProjectMemberRequest,
  ProjectMember,
  ProjectMemberRole,
  ProjectMembersResponse,
} from '@/types/api'

const memberKey = {
  list: (projectId: string) => ['members', projectId] as const,
}

export function useProjectMembers(projectId: string) {
  return useQuery({
    queryKey: memberKey.list(projectId),
    queryFn: async (): Promise<ProjectMembersResponse> => {
      const res = await api.get<ProjectMembersResponse>(
        `/projects/${projectId}/members`,
      )
      return res.data
    },
    enabled: Boolean(projectId),
  })
}

export function useAddMember(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: AddProjectMemberRequest) => {
      const res = await api.post<ProjectMember>(
        `/projects/${projectId}/members`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKey.list(projectId) })
    },
  })
}

export function useUpdateMemberRole(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      userId,
      role,
    }: { userId: string; role: ProjectMemberRole }) => {
      const res = await api.patch<ProjectMember>(
        `/projects/${projectId}/members/${userId}`,
        { role },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKey.list(projectId) })
    },
  })
}

export function useRemoveMember(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) => {
      await api.delete(`/projects/${projectId}/members/${userId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: memberKey.list(projectId) })
    },
  })
}
