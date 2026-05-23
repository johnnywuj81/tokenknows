/**
 * useNodeEntity · v1.3.1 T96 / v1.5 T98 · 节点 → project entity + sources + merge/split.
 *
 * 调用 GET /assets/:aid/nodes/:nid/entity (拿到 entity_id),
 * 再调 GET /entities/:eid/sources 拿跨 asset source 列表.
 *
 * 缓存策略: assess 完成后 entity 稳定, staleTime=5min; 节点 ID 切换才重 fetch.
 * T98 mutations: merge/split 成功后 invalidate 整个 ['kg', 'node-entity'].
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, isApiError } from '@/lib/api'

export interface NodeEntity {
  id: string
  project_id: string
  type: 'person' | 'event' | 'concept' | 'artifact'
  label: string
  canonical_label: string
  aliases: string[]
  source_refs: Array<{
    asset_id: string
    chapter_id: string
    node_id: string
  }>
}

export interface EntitySource {
  asset_id: string
  asset_title: string
  asset_type: string
  chapter_ids: string[]
  node_ids: string[]
}

interface NodeEntityResult {
  entity: NodeEntity | null
  sources: EntitySource[]
}

async function _fetch(
  assetId: string,
  nodeId: string,
): Promise<NodeEntityResult> {
  try {
    const { data: entity } = await api.get<NodeEntity>(
      `/assets/${assetId}/nodes/${nodeId}/entity`,
    )
    const { data: sources } = await api.get<EntitySource[]>(
      `/entities/${entity.id}/sources`,
    )
    return { entity, sources }
  } catch (err) {
    if (isApiError(err) && err.status === 404) {
      return { entity: null, sources: [] }
    }
    throw err
  }
}

export function useNodeEntity(
  assetId: string | null | undefined,
  nodeId: string | null | undefined,
) {
  return useQuery({
    queryKey: ['kg', 'node-entity', assetId, nodeId],
    queryFn: () => _fetch(assetId!, nodeId!),
    enabled: Boolean(assetId && nodeId),
    staleTime: 5 * 60 * 1000,
  })
}


// ── v1.5 T98 · merge / split mutations ────────────────────────────


interface MergeArgs {
  sourceId: string
  targetId: string
}

export function useMergeEntities() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ sourceId, targetId }: MergeArgs) => {
      const { data } = await api.post<{ target: NodeEntity }>(
        `/entities/${sourceId}/merge`,
        { target_id: targetId },
      )
      return data.target
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kg', 'node-entity'] })
      qc.invalidateQueries({ queryKey: ['kg', 'project-entities'] })
    },
  })
}


interface SplitArgs {
  entityId: string
  assetId: string
  nodeId: string
  newLabel?: string
}

export function useSplitNode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ entityId, assetId, nodeId, newLabel }: SplitArgs) => {
      const { data } = await api.post<{
        source: NodeEntity
        new_entity: NodeEntity
      }>(
        `/entities/${entityId}/split`,
        { asset_id: assetId, node_id: nodeId, new_label: newLabel ?? null },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kg', 'node-entity'] })
      qc.invalidateQueries({ queryKey: ['kg', 'project-entities'] })
    },
  })
}


// ── v1.5 T99 · global entity (cross-project) ─────────────────────


export interface GlobalEntity {
  id: string
  type: 'person' | 'event' | 'concept' | 'artifact'
  label: string
  canonical_label: string
  aliases: string[]
  linked: Array<{ project_id: string; project_entity_id: string }>
  created_by: string | null
  project_count: number
}

/** GET /entities/:eid/global · 反查 project entity → global. 404 → null. */
export function useGlobalEntityForProjectEntity(
  projectEntityId: string | null | undefined,
) {
  return useQuery({
    queryKey: ['kg', 'global-for-project-entity', projectEntityId],
    queryFn: async () => {
      try {
        const { data } = await api.get<GlobalEntity>(
          `/entities/${projectEntityId}/global`,
        )
        return data
      } catch (err) {
        if (isApiError(err) && err.status === 404) return null
        throw err
      }
    },
    enabled: Boolean(projectEntityId),
    staleTime: 60 * 1000,
  })
}

export function usePublishEntityToGlobal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (projectEntityId: string) => {
      const { data } = await api.post<GlobalEntity>(
        `/entities/${projectEntityId}/publish_global`,
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kg', 'global-for-project-entity'] })
      qc.invalidateQueries({ queryKey: ['kg', 'global-entities'] })
    },
  })
}

export function useUnlinkEntityFromGlobal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (projectEntityId: string) => {
      await api.delete(`/entities/${projectEntityId}/global`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kg', 'global-for-project-entity'] })
      qc.invalidateQueries({ queryKey: ['kg', 'global-entities'] })
    },
  })
}
