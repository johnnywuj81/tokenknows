/**
 * useNodeEntity · v1.3.1 T96 · 节点 → project entity 反查 + 该 entity 的 sources.
 *
 * 调用 GET /assets/:aid/nodes/:nid/entity (拿到 entity_id),
 * 再调 GET /entities/:eid/sources 拿跨 asset source 列表.
 *
 * 缓存策略: assess 完成后 entity 稳定, staleTime=5min; 节点 ID 切换才重 fetch.
 */

import { useQuery } from '@tanstack/react-query'
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
