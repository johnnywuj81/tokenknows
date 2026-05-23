/**
 * KnowledgeGraphView · v1.2.1 T88 · DocumentPage 的 KG 分支容器.
 *
 * 抽出原因: useChapterEvidence 不能在 DocumentPage 主体的 if 分支后调用
 * (违反 React Hooks rules); 抽成子组件每次都无条件 hook.
 *
 * 职责:
 *   - 用 useChapterEvidence 拉 KG chapter 的 evidence 列表
 *   - 收到 KnowledgeGraphPage onNodeClick 时, 按 node.source_event_ids 找匹配
 *     evidence_id, 触发 openEvidence(chapter_id, evidence_id)
 *   - 没有匹配时 fallback: openEvidence(chapter_id, null) (打开 drawer 默认第一条)
 */

import { useCallback } from 'react'
import type { Asset, Chapter, KGNode } from '@/types/api'
import { DocHeader } from '../page/components/DocHeader'
import KnowledgeGraphPage from './KnowledgeGraphPage'
import { useChapterEvidence } from '../hooks/useChapterEvidence'

interface KnowledgeGraphViewProps {
  asset: Asset
  chapter: Chapter
  onSubmit: () => void
  submitting: boolean
  onPublish: () => void
  /** DocumentPage.handleViewEvidence(chapterId, evidenceId|null) */
  onOpenEvidence: (chapterId: string, evidenceId?: string) => void
}

export function KnowledgeGraphView({
  asset,
  chapter,
  onSubmit,
  submitting,
  onPublish,
  onOpenEvidence,
}: KnowledgeGraphViewProps) {
  const evidenceQuery = useChapterEvidence(asset.id, chapter.id)
  const evidences = evidenceQuery.data ?? []

  const handleNodeClick = useCallback(
    (node: KGNode): void => {
      // 找第一条 evidence.event_id ∈ node.source_event_ids
      const eventIds = new Set(node.source_event_ids)
      const match = evidences.find((ev) => eventIds.has(ev.event_id))
      if (match) {
        onOpenEvidence(chapter.id, match.id)
      } else {
        // 节点没有 evidence 关联 → 仍打开 drawer (默认第一条)
        onOpenEvidence(chapter.id, undefined)
      }
    },
    [evidences, chapter.id, onOpenEvidence],
  )

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <DocHeader
        asset={asset}
        onSubmit={onSubmit}
        submitting={submitting}
        onPublish={onPublish}
      />
      <KnowledgeGraphPage chapter={chapter} onNodeClick={handleNodeClick} />
    </div>
  )
}
