/**
 * lod · v1.3.1 T94 LOD 聚类纯函数单测.
 *
 * 验:
 *   - 小图 (<threshold) 返回原样
 *   - 大图按 type + trust_score top-K 保留, 余则聚类
 *   - 边端点重写 + 内部边丢弃 + 去重
 *   - expanded 集合优先级 (用户点开)
 *   - 边界: 单个 type 全部都聚 / type 数量 < 4 / 同分稳定排序
 */

import { describe, it, expect } from 'vitest'
import { clusterLayout, isSuperNode, type KGSuperNode } from './lod'
import type { KGEdge, KGNode } from '@/types/api'

function mkNode(
  id: string,
  type: KGNode['type'],
  trust = 0.5,
  label?: string,
): KGNode {
  return {
    id,
    type,
    label: label ?? id,
    summary: null,
    properties: {},
    source_event_ids: [],
    trust_score: trust,
    span_anchor: null,
  }
}

function mkEdge(
  id: string,
  source: string,
  target: string,
  etype: KGEdge['type'] = 'related_to',
): KGEdge {
  return {
    id, source, target, type: etype,
    label: null, weight: 1, source_event_ids: [],
  }
}

describe('clusterLayout', () => {
  it('小图 (节点数 < threshold) 原样返回, clustered=false', () => {
    const nodes = Array.from({ length: 50 }, (_, i) =>
      mkNode(`n${i}`, 'person', 0.5),
    )
    const edges: KGEdge[] = []
    const r = clusterLayout({ nodes, edges })
    expect(r.clustered).toBe(false)
    expect(r.visibleNodes).toHaveLength(50)
    expect(r.hiddenByType.person).toBe(0)
  })

  it('大图按 type top-K 保留, 余则聚成 supernode', () => {
    // 60 person + 60 event = 120 nodes (> 100 默认 threshold)
    const persons = Array.from({ length: 60 }, (_, i) =>
      mkNode(`p${i}`, 'person', 1.0 - i * 0.01),
    )
    const events = Array.from({ length: 60 }, (_, i) =>
      mkNode(`e${i}`, 'event', 1.0 - i * 0.01),
    )
    const r = clusterLayout({ nodes: [...persons, ...events], edges: [] })
    expect(r.clustered).toBe(true)
    // perTypeKeep=20 默认; 每个 type 留 20 + 1 supernode = 21
    // 总: 21 + 21 = 42
    expect(r.visibleNodes).toHaveLength(42)
    const personSuper = r.visibleNodes.find(
      (n): n is KGSuperNode => isSuperNode(n) && n.child_type === 'person',
    )
    expect(personSuper).toBeTruthy()
    expect(personSuper!.children).toHaveLength(40)
    expect(personSuper!.label).toMatch(/40/)
    expect(r.hiddenByType.person).toBe(40)
    expect(r.hiddenByType.event).toBe(40)
  })

  it('保留的 top-K 是 trust_score 最高的', () => {
    const nodes = Array.from({ length: 120 }, (_, i) =>
      mkNode(`n${i}`, 'person', i / 120),  // 0..1, 越大 trust 越高
    )
    const r = clusterLayout({ nodes, edges: [] })
    // 可见原节点 (排除 supernode) 应该都是 trust >= 100/120
    const visibleOrig = r.visibleNodes.filter(
      (n): n is KGNode => !isSuperNode(n),
    )
    expect(visibleOrig).toHaveLength(20)
    for (const n of visibleOrig) {
      expect(n.trust_score).toBeGreaterThanOrEqual(100 / 120)
    }
  })

  it('边: 两端都可见 → 保留原 id', () => {
    // 50 person + 100 event = 150 nodes
    const persons = Array.from({ length: 50 }, (_, i) =>
      mkNode(`p${i}`, 'person', 0.9),
    )
    const events = Array.from({ length: 100 }, (_, i) =>
      mkNode(`e${i}`, 'event', 0.5),
    )
    // 边: p0 → p1 (两个 person 都可见, person 总共 50 < 20? 不, 50 > 20, 所以 top 20 留)
    // 实际 p0 trust 都是 0.9, label asc 排序, p0 在前 20 个里
    const edges = [mkEdge('eA', 'p0', 'p1')]
    const r = clusterLayout({
      nodes: [...persons, ...events],
      edges,
    })
    // p0 / p1 是 top 20 in person (按 label asc 同分稳定 → p0..p19 留下)
    const p0Visible = r.visibleNodes.some((n) => n.id === 'p0')
    const p1Visible = r.visibleNodes.some((n) => n.id === 'p1')
    expect(p0Visible).toBe(true)
    expect(p1Visible).toBe(true)
    // 边保留, id 不变
    expect(r.visibleEdges.find((e) => e.id === 'eA')).toBeTruthy()
  })

  it('边: 一端被聚类 → 重写到 supernode, id 加 __lod 后缀', () => {
    // 1 个 person 可见 + 25 个被聚 (perTypeKeep=20)
    // 加 100 event 凑 > threshold
    const nodes: KGNode[] = [
      // 25 person, trust 1.0 → top 20 留, p20..p24 被聚
      ...Array.from({ length: 25 }, (_, i) =>
        mkNode(`p${i}`, 'person', 1.0, `p${String(i).padStart(2, '0')}`),
      ),
      // 100 event, trust 0.5 → top 20 留, 余 80 被聚
      ...Array.from({ length: 100 }, (_, i) =>
        mkNode(`e${i}`, 'event', 0.5, `e${String(i).padStart(3, '0')}`),
      ),
    ]
    // 边: p00 (可见) → p23 (被聚)
    const edges = [mkEdge('eX', 'p00', 'p23', 'mentions')]
    const r = clusterLayout({ nodes, edges })
    const edge = r.visibleEdges.find((e) => e.source === 'p00')
    expect(edge).toBeTruthy()
    expect(edge!.target).toBe('cluster_person')
    expect(edge!.id).toBe('eX__lod')
  })

  it('边: 两端在同一 supernode 内 → 丢弃 (self-loop)', () => {
    // 22 person trust 1.0, top 20 留 (p00..p19), p20+p21 入 supernode
    const nodes = Array.from({ length: 22 }, (_, i) =>
      mkNode(`p${i}`, 'person', 1.0, `p${String(i).padStart(2, '0')}`),
    ).concat(
      Array.from({ length: 100 }, (_, i) =>
        mkNode(`e${i}`, 'event', 0.3),
      ),
    )
    // p20 → p21 (两个都被聚类, 同 supernode)
    const edges = [mkEdge('eSelf', 'p20', 'p21')]
    const r = clusterLayout({ nodes, edges })
    // self-loop 丢弃
    expect(r.visibleEdges).toHaveLength(0)
  })

  it('多条边重写后端点 + type 相同 → 去重', () => {
    const nodes = Array.from({ length: 100 }, (_, i) =>
      mkNode(`p${i}`, 'person', 1.0, `p${String(i).padStart(3, '0')}`),
    ).concat(Array.from({ length: 50 }, (_, i) => mkNode(`e${i}`, 'event', 0.3)))
    // 20 person 留, 80 被聚类
    // 加 3 条边都从 e0 指向被聚的 person, type 一致 → 只剩 1 条
    const edges = [
      mkEdge('e1', 'e0', 'p99', 'mentions'),
      mkEdge('e2', 'e0', 'p90', 'mentions'),
      mkEdge('e3', 'e0', 'p80', 'mentions'),
    ]
    const r = clusterLayout({ nodes, edges })
    const toCluster = r.visibleEdges.filter(
      (e) => e.target === 'cluster_person' && e.type === 'mentions',
    )
    expect(toCluster).toHaveLength(1)
  })

  it('expanded 集合: 该 type 不聚类 (用户展开)', () => {
    const nodes = Array.from({ length: 60 }, (_, i) =>
      mkNode(`p${i}`, 'person', 0.5),
    ).concat(
      Array.from({ length: 60 }, (_, i) => mkNode(`e${i}`, 'event', 0.5)),
    )
    const expanded = new Set<KGNode['type']>(['person'])
    const r = clusterLayout({ nodes, edges: [] }, { expanded })
    // person 不聚 (60 个全可见), event 聚 (20 留 + 1 super)
    const personNodes = r.visibleNodes.filter(
      (n): n is KGNode => !isSuperNode(n) && n.type === 'person',
    )
    expect(personNodes).toHaveLength(60)
    const eventSuper = r.visibleNodes.find(
      (n): n is KGSuperNode => isSuperNode(n) && n.child_type === 'event',
    )
    expect(eventSuper).toBeTruthy()
    expect(eventSuper!.children).toHaveLength(40)
  })

  it('自定义 threshold / perTypeKeep', () => {
    const nodes = Array.from({ length: 30 }, (_, i) =>
      mkNode(`n${i}`, 'person', 0.5),
    )
    // threshold=20 触发聚类; perTypeKeep=5 留 5
    const r = clusterLayout(
      { nodes, edges: [] },
      { threshold: 20, perTypeKeep: 5 },
    )
    expect(r.clustered).toBe(true)
    expect(r.visibleNodes).toHaveLength(6)  // 5 留 + 1 super
    expect(r.hiddenByType.person).toBe(25)
  })

  it('单 type 不足 perTypeKeep 时不创建 supernode', () => {
    // 110 nodes 触发 threshold, 但每 type 单独 <= 20
    // person=20, event=20, concept=20, artifact=50 → 只 artifact 聚
    const persons = Array.from({ length: 20 }, (_, i) =>
      mkNode(`p${i}`, 'person', 0.5),
    )
    const events = Array.from({ length: 20 }, (_, i) =>
      mkNode(`e${i}`, 'event', 0.5),
    )
    const concepts = Array.from({ length: 20 }, (_, i) =>
      mkNode(`c${i}`, 'concept', 0.5),
    )
    const artifacts = Array.from({ length: 50 }, (_, i) =>
      mkNode(`a${i}`, 'artifact', 0.5),
    )
    const r = clusterLayout({
      nodes: [...persons, ...events, ...concepts, ...artifacts],
      edges: [],
    })
    expect(r.clustered).toBe(true)
    expect(r.hiddenByType.person).toBe(0)
    expect(r.hiddenByType.event).toBe(0)
    expect(r.hiddenByType.concept).toBe(0)
    expect(r.hiddenByType.artifact).toBe(30)
    // person/event/concept supernode 不存在
    const superCount = r.visibleNodes.filter(isSuperNode).length
    expect(superCount).toBe(1)
  })

  it('isSuperNode 类型守卫正常工作', () => {
    const reg = mkNode('n', 'person')
    const sup: KGSuperNode = {
      id: 'cluster_event', type: 'cluster',
      label: '其他 N 事件', child_type: 'event',
      children: [], avg_trust: 0,
    }
    expect(isSuperNode(reg)).toBe(false)
    expect(isSuperNode(sup)).toBe(true)
  })
})
