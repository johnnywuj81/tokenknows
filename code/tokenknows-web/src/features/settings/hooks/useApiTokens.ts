/**
 * useApiTokens · Phase B TanStack Query hooks for 个人 API token (MCP 接入).
 *
 * 端点 (后端 Phase A):
 *   GET    /me/tokens        → ApiTokensListResponse
 *   POST   /me/tokens        → 201 CreateApiTokenResponse (明文只返回一次)
 *   DELETE /me/tokens/{id}   → 204
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  ApiTokensListResponse,
  CreateApiTokenRequest,
  CreateApiTokenResponse,
} from '@/types/api'

const tokenKey = {
  list: () => ['me', 'tokens'] as const,
}

export function useApiTokens() {
  return useQuery({
    queryKey: tokenKey.list(),
    queryFn: async (): Promise<ApiTokensListResponse> => {
      const res = await api.get<ApiTokensListResponse>('/me/tokens')
      return res.data
    },
  })
}

export function useCreateApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (
      body: CreateApiTokenRequest,
    ): Promise<CreateApiTokenResponse> => {
      const res = await api.post<CreateApiTokenResponse>('/me/tokens', body)
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tokenKey.list() })
    },
  })
}

export function useRevokeApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tokenId: string) => {
      await api.delete(`/me/tokens/${tokenId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tokenKey.list() })
    },
  })
}
