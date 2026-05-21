/**
 * useRedaction · T10 脱敏扫描 + 确认 + 豁免 hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApiError, RedactionScanJob } from '@/types/api'

function isNotFound(err: unknown): boolean {
  // api.ts interceptor 归一化为 ApiError { status, code, ... }
  return (
    typeof err === 'object' &&
    err !== null &&
    'status' in err &&
    (err as ApiError).status === 404
  )
}

// ─── 扫描结果 (query) ────────────────────────────────────────

export function useRedactionScan(assetId: string | null | undefined) {
  return useQuery({
    queryKey: ['assets', assetId, 'redaction'],
    queryFn: async (): Promise<RedactionScanJob | null> => {
      try {
        const { data } = await api.get<RedactionScanJob>(
          `/assets/${assetId}/redaction/scan`,
        )
        return data
      } catch (err: unknown) {
        if (isNotFound(err)) return null
        throw err
      }
    },
    enabled: Boolean(assetId),
    retry: (failureCount, err) => {
      // 404 不 retry (尚未扫描是正常状态)
      if (isNotFound(err)) return false
      return failureCount < 2
    },
  })
}

// ─── 触发扫描 (mutation) ─────────────────────────────────────

export function useTriggerRedactionScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (assetId: string): Promise<RedactionScanJob> => {
      const { data } = await api.post<RedactionScanJob>(
        `/assets/${assetId}/redaction/scan`,
      )
      return data
    },
    onSuccess: (_data, assetId) => {
      void qc.invalidateQueries({ queryKey: ['assets', assetId, 'redaction'] })
      void qc.invalidateQueries({ queryKey: ['assets', assetId] })
    },
  })
}

// ─── 确认 (mutation) ─────────────────────────────────────────

interface ConfirmVars {
  assetId: string
  itemIds: string[]
}

export function useConfirmRedaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: ConfirmVars): Promise<RedactionScanJob> => {
      const { data } = await api.post<RedactionScanJob>(
        `/assets/${vars.assetId}/redaction/confirm`,
        { item_ids: vars.itemIds },
      )
      return data
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId, 'redaction'] })
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId] })
    },
  })
}

// ─── 豁免 (mutation) ─────────────────────────────────────────

interface ExemptVars {
  assetId: string
  itemId: string
  reason: string
}

export function useExemptRedaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: ExemptVars): Promise<RedactionScanJob> => {
      const { data } = await api.post<RedactionScanJob>(
        `/assets/${vars.assetId}/redaction/exempt`,
        { item_id: vars.itemId, reason: vars.reason },
      )
      return data
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId, 'redaction'] })
      void qc.invalidateQueries({ queryKey: ['assets', vars.assetId] })
    },
  })
}
