/**
 * lod · v1.3.1 T94 · 大图 (>100 nodes) Level-of-Detail 聚类.
 *
 * 算法:
 *   1. 节点数 ≤ threshold → 原样返回 (no-op, 兼容 < 100 节点小图)
 *   2. 按 type 分组 (person/event/concept/artifact)
 *   3. 每个 type 内按 trust_score 降序, 保留 top-K 单独可见
 *   4. 剩余节点合并成 1 个 supernode (id="cluster_<type>"), label "Other N persons"
 *   5. 边: source/target 都在可见集合 → 保留; 任一被聚类 → 重写到对应 supernode
 *   6. 同 supernode 的 self-loop 自动丢弃
 *   7. expand(id) 后该 type 的 supernode "破开", 全部 N 个节点重新可见
 *
 * 限制: 纯函数, 不改 layout; supernode 携带 children 字段供 UI 展开.
 */

import type { KGEdge, KGNode, KnowledgeGraphLayout } from '@/types/api'

/** v1.3.1 T94 · supernode 元节点 (UI 渲染时识别). */
export interface KGSuperNode {
  id: string                  // "cluster_person"
  type: 'cluster'             // 自定义 type, GraphCanvas 用专用渲染
  label: string               // "其他 23 人"
  child_type: KGNode['type']  // 原 type, 用于 expand
  children: KGNode[]          // 被聚类的子节点
  /** 平均 trust, 给视觉用 */
  avg_trust: number
}

export interface LODResult {
  /** 视觉上要渲染的: 可见原节点 + supernode */
  visibleNodes: Array<KGNode | KGSuperNode>
  /** 重写后的边: 端点为 supernode id 或 原 node id */
  visibleEdges: KGEdge[]
  /** 是否真的聚类了 (UI 决定是否显示 "已聚类 N 个" 提示) */
  clustered: boolean
  /** 各 type 的聚类后数量 (UI 可显示) */
  hiddenByType: Record<KGNode['type'], number>
}

export interface ClusterOptions {
  /** 节点数 < threshold 时不聚类. 默认 100. */
  threshold?: number
  /** 每个 type 保留可见的 top-K. 默认 20. */
  perTypeKeep?: number
  /** 强制展开的 type 集合 (用户点 supernode 展开时传入) */
  expanded?: Set<KGNode['type']>
}

const DEFAULT_THRESHOLD = 100
const DEFAULT_PER_TYPE_KEEP = 20

const ALL_TYPES: KGNode['type'][] = ['person', 'event', 'concept', 'artifact']

const TYPE_LABEL_ZH: Record<KGNode['type'], string> = {
  person: '人',
  event: '事件',
  concept: '概念',
  artifact: '产物',
}

/** 是否为 supernode (类型守卫). */
export function isSuperNode(n: KGNode | KGSuperNode): n is KGSuperNode {
  return n.type === ('cluster' as KGSuperNode['type'])
}

/**
 * LOD 聚类入口.
 *
 * @param layout 完整 KG layout
 * @param opts cluster 参数 + expanded set
 * @returns 视觉节点/边 + 聚类元信息
 */
export function clusterLayout(
  layout: Pick<KnowledgeGraphLayout, 'nodes' | 'edges'>,
  opts: ClusterOptions = {},
): LODResult {
  const threshold = opts.threshold ?? DEFAULT_THRESHOLD
  const perTypeKeep = opts.perTypeKeep ?? DEFAULT_PER_TYPE_KEEP
  const expanded = opts.expanded ?? new Set<KGNode['type']>()

  const hiddenByType: Record<KGNode['type'], number> = {
    person: 0, event: 0, concept: 0, artifact: 0,
  }

  // 小图直接返回
  if (layout.nodes.length < threshold) {
    return {
      visibleNodes: [...layout.nodes],
      visibleEdges: [...layout.edges],
      clustered: false,
      hiddenByType,
    }
  }

  // 1. 按 type 分组
  const byType = new Map<KGNode['type'], KGNode[]>()
  for (const t of ALL_TYPES) byType.set(t, [])
  for (const n of layout.nodes) {
    byType.get(n.type)?.push(n)
  }

  // 2. 每个 type 取 top-K (trust desc); 多余的入 supernode
  const visibleNodes: Array<KGNode | KGSuperNode> = []
  /** nodeId → supernodeId (用于边端点重写) */
  const nodeToSuper = new Map<string, string>()
  let didCluster = false

  for (const t of ALL_TYPES) {
    const list = byType.get(t) ?? []
    if (list.length === 0) continue

    // expanded 的 type 全部可见
    if (expanded.has(t)) {
      visibleNodes.push(...list)
      continue
    }

    if (list.length <= perTypeKeep) {
      visibleNodes.push(...list)
      continue
    }

    // 按 trust_score 降序, 同分按 label asc 稳定
    const sorted = [...list].sort((a, b) => {
      if (b.trust_score !== a.trust_score) return b.trust_score - a.trust_score
      return a.label.localeCompare(b.label)
    })
    const kept = sorted.slice(0, perTypeKeep)
    const hidden = sorted.slice(perTypeKeep)
    visibleNodes.push(...kept)

    const superId = `cluster_${t}`
    const avg_trust = hidden.length
      ? hidden.reduce((s, n) => s + n.trust_score, 0) / hidden.length
      : 0
    visibleNodes.push({
      id: superId,
      type: 'cluster',
      label: `其他 ${hidden.length} 个${TYPE_LABEL_ZH[t]}`,
      child_type: t,
      children: hidden,
      avg_trust,
    })
    for (const h of hidden) nodeToSuper.set(h.id, superId)
    hiddenByType[t] = hidden.length
    didCluster = true
  }

  // 3. 重写边
  /** dedup key: "src>tgt:type" */
  const seenEdgeKeys = new Set<string>()
  const visibleEdges: KGEdge[] = []
  for (const e of layout.edges) {
    const src = nodeToSuper.get(e.source) ?? e.source
    const tgt = nodeToSuper.get(e.target) ?? e.target
    if (src === tgt) continue  // 同 supernode 内部边丢弃
    const key = `${src}>${tgt}:${e.type}`
    if (seenEdgeKeys.has(key)) continue
    seenEdgeKeys.add(key)
    visibleEdges.push({
      ...e,
      id: src === e.source && tgt === e.target ? e.id : `${e.id}__lod`,
      source: src,
      target: tgt,
    })
  }

  return {
    visibleNodes,
    visibleEdges,
    clustered: didCluster,
    hiddenByType,
  }
}
