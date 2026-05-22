/**
 * useIMConnections · TanStack Query hooks for v0.3 IM API
 *
 * 端点对应:
 *   GET    /projects/:id/im/connections             → useIMConnections
 *   POST   /projects/:id/im/connections             → useCreateIMConnection
 *   PATCH  /im/connections/:cid                     → useUpdateIMConnection
 *   DELETE /im/connections/:cid                     → useRevokeIMConnection
 *   GET    /im/connections/:cid/chats               → useIMChats
 *   POST   .../chats/:cid/join                      → useJoinChat
 *   POST   .../chats/:cid/leave                     → useLeaveChat
 *   GET    .../chats/:cid/stats                     → useChatStats
 *   POST   .../distill                              → useDistillIMChat
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  CreateIMConnectionRequest,
  CreateIMConnectionResponse,
  DistillIMRequest,
  DistillIMResponse,
  IMChat,
  IMChatStats,
  IMConnection,
  IMConnectionStatus,
} from '@/types/api'

const imKey = {
  list: (pid: string, status?: IMConnectionStatus) =>
    ['im', pid, 'connections', status ?? 'all'] as const,
  chats: (cid: string) => ['im', cid, 'chats'] as const,
  stats: (cid: string, chatId: string) => ['im', cid, 'chats', chatId, 'stats'] as const,
}

export function useIMConnections(
  projectId: string,
  status?: IMConnectionStatus,
) {
  return useQuery({
    queryKey: imKey.list(projectId, status),
    queryFn: async () => {
      const search = status ? `?status=${status}` : ''
      const res = await api.get<IMConnection[]>(
        `/projects/${projectId}/im/connections${search}`,
      )
      return res.data
    },
    enabled: Boolean(projectId),
  })
}

export function useCreateIMConnection(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CreateIMConnectionRequest) => {
      const res = await api.post<CreateIMConnectionResponse>(
        `/projects/${projectId}/im/connections`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['im', projectId] })
    },
  })
}

export function useUpdateIMConnection(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      connectionId,
      status,
    }: { connectionId: string; status: IMConnectionStatus }) => {
      const res = await api.patch<IMConnection>(
        `/im/connections/${connectionId}`,
        { status },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['im', projectId] })
    },
  })
}

export function useRevokeIMConnection(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (connectionId: string) => {
      await api.delete(`/im/connections/${connectionId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['im', projectId] })
    },
  })
}

export function useIMChats(connectionId: string | null) {
  return useQuery({
    queryKey: imKey.chats(connectionId ?? ''),
    queryFn: async () => {
      const res = await api.get<IMChat[]>(`/im/connections/${connectionId}/chats`)
      return res.data
    },
    enabled: Boolean(connectionId),
  })
}

export function useJoinChat(connectionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (chatId: string) => {
      const res = await api.post(
        `/im/connections/${connectionId}/chats/${chatId}/join`,
        {},
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: imKey.chats(connectionId) })
    },
  })
}

export function useLeaveChat(connectionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (chatId: string) => {
      const res = await api.post(
        `/im/connections/${connectionId}/chats/${chatId}/leave`,
        {},
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: imKey.chats(connectionId) })
    },
  })
}

export function useChatStats(connectionId: string, chatId: string | null) {
  return useQuery({
    queryKey: imKey.stats(connectionId, chatId ?? ''),
    queryFn: async () => {
      const res = await api.get<IMChatStats>(
        `/im/connections/${connectionId}/chats/${chatId}/stats`,
      )
      return res.data
    },
    enabled: Boolean(connectionId && chatId),
  })
}

export function useDistillIMChat(connectionId: string) {
  return useMutation({
    mutationFn: async (body: DistillIMRequest) => {
      const res = await api.post<DistillIMResponse>(
        `/im/connections/${connectionId}/distill`,
        body,
      )
      return res.data
    },
  })
}

// ─── v0.3.1 G · SignalGate config ─────────────────────────

export interface SignalConfig {
  threshold: number
  llm_model: string | null
}

export function useSignalConfig(projectId: string) {
  return useQuery({
    queryKey: ['im', projectId, 'signal-config'] as const,
    queryFn: async () => {
      const res = await api.get<SignalConfig>(
        `/projects/${projectId}/im/signal/config`,
      )
      return res.data
    },
    enabled: Boolean(projectId),
  })
}

export function useUpdateSignalConfig(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (
      body: { threshold?: number; llm_model?: string | null },
    ) => {
      const res = await api.patch<SignalConfig>(
        `/projects/${projectId}/im/signal/config`,
        body,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['im', projectId, 'signal-config'] })
    },
  })
}

// ─── v0.3.1 H · Distill 异步 + SSE ─────────────────────────

export interface DistillJobInfo {
  job_id: string
  connection_id: string
  chat_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  messages_total: number
  messages_processed: number
  segments_persisted: number
  segment_ids: string[]
  error: string | null
}

export function useTriggerDistillAsync(connectionId: string) {
  return useMutation({
    mutationFn: async (
      body: DistillIMRequest,
    ): Promise<DistillJobInfo> => {
      const res = await api.post<DistillJobInfo>(
        `/im/connections/${connectionId}/distill-async`,
        body,
      )
      return res.data
    },
  })
}

export function useDistillJob(jobId: string | null) {
  return useQuery({
    queryKey: ['im', 'distill-job', jobId ?? ''] as const,
    queryFn: async () => {
      const res = await api.get<DistillJobInfo>(`/im/distill-jobs/${jobId}`)
      return res.data
    },
    enabled: Boolean(jobId),
    refetchInterval: (q) => {
      // 终态停止轮询
      const data = q.state.data as DistillJobInfo | undefined
      if (!data) return 2000
      if (data.status === 'completed' || data.status === 'failed') return false
      return 2000
    },
  })
}
