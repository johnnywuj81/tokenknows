/**
 * useGenerateAsset · POST /api/v1/projects/:id/assets/generate
 *
 * 返回 generating 状态的 Asset, 5s 后 polling 自动转 draft (见 useAssets)。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Asset, AssetType } from '@/types/api'

export interface GeneratePayload {
  projectId: string
  type: AssetType
  time_window?: string
  source_filter?: Record<string, unknown>
  model_override?: string
  /** T106 · 显式 provider, 后端优先用 (rather than guess from model name). */
  provider_override?: string
  /**
   * A 改造 · 用户在 dialog 输入的主题提示.
   * - 后端 collect 阶段用关键词过滤 events
   * - distill prompt 里告知 LLM "只围绕该主题"
   * 对 agent_skill 类型尤其重要 (避免多主题混在一份 skill 里).
   */
  topic_hint?: string
}

async function generateAssetRequest(payload: GeneratePayload): Promise<Asset> {
  const { data } = await api.post<Asset>(`/projects/${payload.projectId}/assets/generate`, {
    type: payload.type,
    time_window: payload.time_window,
    source_filter: payload.source_filter,
    model_override: payload.model_override,
    provider_override: payload.provider_override,
    topic_hint: payload.topic_hint,
  })
  return data
}

export function useGenerateAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: generateAssetRequest,
    onSuccess: (_, vars) => {
      // 触发列表立即刷新看到新 generating 卡片
      queryClient.invalidateQueries({
        queryKey: ['projects', vars.projectId, 'assets'],
      })
    },
  })
}
