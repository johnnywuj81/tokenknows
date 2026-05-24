/**
 * T09 · ReviewPage (Reviewer 审批视图)
 *
 * 三栏:
 *   [左] DocOutline (复用 T06)
 *   [中] 只读 ChapterBlock 列表 (复用 T06 + readOnly)
 *   [右] ApprovalSidebar - 章节级审批进度 + 通过/退回操作
 *
 * 底部固定: BottomActionBar (全部通过 → 跳 T11 / 退回修改 → 回 T06 / 保存进度)
 *
 * 设计依据: 任务包 T09 §4-§8
 */

import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useAsset } from '../documents/hooks/useAsset'
import { useChapters } from '../documents/hooks/useChapters'
import { useChapterEvidence } from '../documents/hooks/useChapterEvidence'
import { DocOutline } from '../documents/page/components/DocOutline'
import { ChapterBlock } from '../documents/page/components/ChapterBlock'
import { EvidenceDrawer } from '../documents/page/components/EvidenceDrawer'
import { GraphCanvas } from '../documents/knowledge-graph/GraphCanvas'
import { ReviewerNodeTable } from '../documents/knowledge-graph/ReviewerNodeTable'
import type { KGNode, KnowledgeGraphLayout } from '@/types/api'
import { ApprovalSidebar } from './components/ApprovalSidebar'
import { BottomActionBar } from './components/BottomActionBar'

export default function ReviewPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>()
  const navigate = useNavigate()
  const assetQuery = useAsset(docId)
  const chaptersQuery = useChapters(docId)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [scrollToChapterId, setScrollToChapterId] = useState<string | null>(null)

  const openEvidence = useDocumentUiStore((s) => s.openEvidence)
  const handleViewEvidence = useCallback(
    (chapterId: string, evidenceId?: string) => {
      openEvidence(chapterId, evidenceId ?? null)
    },
    [openEvidence],
  )

  const isLoading = assetQuery.isLoading || chaptersQuery.isLoading
  const error = assetQuery.error ?? chaptersQuery.error

  if (error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="审批页加载失败"
        error={error}
        onRetry={() => {
          assetQuery.refetch()
          chaptersQuery.refetch()
        }}
        action={
          <button
            type="button"
            onClick={() => projectId && navigate(`/projects/${projectId}/documents`)}
            className="font-ui text-body-sm text-accent-primary-dark hover:underline"
          >
            返回文档列表
          </button>
        }
      />
    )
  }

  if (isLoading || !assetQuery.data) {
    return <LoadingSkeleton variant="document" />
  }

  const asset = assetQuery.data
  const chapters = chaptersQuery.data ?? []
  // T125 · 提前算一次 KG layout (避免 JSX 里重复调 + 非空断言).
  // chapters 可能为空数组, 此时 firstChapter 为 undefined, kgLayout 也为 null.
  const firstChapter = chapters[0]
  const kgLayout =
    asset.type === 'knowledge_graph' && firstChapter
      ? _kgLayout(firstChapter.layout)
      : null

  function scrollToChapter(id: string) {
    setScrollToChapterId(id)
    const el = document.getElementById(`chapter-anchor-${id}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto]">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border-subtle bg-bg-card px-6 py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => projectId && navigate(`/projects/${projectId}/documents`)}
            className="font-ui text-caption text-text-muted hover:text-text-primary"
          >
            ← 返回文档列表
          </button>
          <h1 className="font-content text-h3 text-text-primary">
            审批 · {asset.title}
          </h1>
          <ApprovalStateBadge state={asset.approval_state} />
        </div>
        <div className="font-ui text-caption text-text-muted">
          {chapters.filter((c) => c.approval_state === 'approved').length} / {chapters.length} 已通过
        </div>
      </header>

      {/* 三栏 */}
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)_360px]">
        {/* 左 · 大纲 */}
        <DocOutline chapters={chapters} scrollRef={scrollRef} />

        {/* 中 · 只读正文 */}
        <main
          ref={scrollRef}
          className="overflow-auto bg-bg-page px-6 py-6"
          aria-label="审批正文"
        >
          {chapters.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border-medium bg-bg-card p-8 text-center">
              <p className="font-content text-h3 text-text-primary">无章节可审批</p>
            </div>
          ) : kgLayout && firstChapter ? (
            // T125 · KG asset 走图谱可视化 + 节点表 (reviewer 主要看实体/关系,
            // 不是 markdown 节点索引). 复用 GraphCanvas (只读) + ReviewerNodeTable.
            <KGReviewSection
              layout={kgLayout}
              chapterId={firstChapter.id}
              assetId={asset.id}
              onViewEvidence={handleViewEvidence}
            />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {chapters.map((ch) => (
                <ChapterBlock
                  key={ch.id}
                  chapter={ch}
                  readOnly
                  onViewEvidence={handleViewEvidence}
                />
              ))}
            </div>
          )}
        </main>

        {/* 右 · 审批进度 */}
        <ApprovalSidebar
          assetId={asset.id}
          chapters={chapters}
          highlightChapterId={scrollToChapterId}
          onScrollToChapter={scrollToChapter}
        />
      </div>

      {/* 底部操作栏 */}
      <BottomActionBar
        asset={asset}
        chapters={chapters}
        projectId={projectId}
        onAllApproved={() => {
          // T11 进入发布: 跳回文档页 + 触发 PublishDialog (经 store)
          if (projectId && docId) {
            useDocumentUiStore.getState().openPublish()
            navigate(`/projects/${projectId}/documents/${docId}`)
          }
        }}
      />

      {/* T07 证据抽屉 (审批视角也允许打开看引用) */}
      <EvidenceDrawer assetId={docId} />
    </div>
  )
}

// ── T125 · KG asset 审批视图辅助 ──────────────────────────────────
//
// 后端把整图 JSON 塞进 `chapter.layout` (dict 字段), 这里做防御性窄化:
// 只有出现 `nodes` 字段 + 数组形态 才认为是有效 KnowledgeGraphLayout,
// 其它情形(空 layout / 旧 markdown chapter / parse_error) 返 null,
// 调用方回退到默认 markdown 渲染.
function _kgLayout(layout: unknown): KnowledgeGraphLayout | null {
  if (!layout || typeof layout !== 'object') return null
  const maybe = layout as { nodes?: unknown; edges?: unknown }
  if (!Array.isArray(maybe.nodes) || !Array.isArray(maybe.edges)) return null
  return layout as KnowledgeGraphLayout
}

interface KGReviewSectionProps {
  layout: KnowledgeGraphLayout
  chapterId: string
  assetId: string
  onViewEvidence: (chapterId: string, evidenceId?: string) => void
}

/**
 * KG 审批主体: 上方 React Flow 图谱 (只读交互, 节点拖动仍允许便于检视) +
 * 下方 ReviewerNodeTable (节点审计表). 节点点击复用 KnowledgeGraphView 同
 * 一套 source_event_ids → evidence_id 匹配逻辑.
 */
function KGReviewSection({
  layout,
  chapterId,
  assetId,
  onViewEvidence,
}: KGReviewSectionProps) {
  const evidenceQuery = useChapterEvidence(assetId, chapterId)
  // 稳定空数组引用避免 useCallback 依赖在每次渲染都变化 (react-hooks/exhaustive-deps).
  const evidences = useMemo(() => evidenceQuery.data ?? [], [evidenceQuery.data])

  const handleNodeClick = useCallback(
    (node: KGNode): void => {
      const eventIds = new Set(node.source_event_ids)
      const match = evidences.find((ev) => eventIds.has(ev.event_id))
      onViewEvidence(chapterId, match?.id)
    },
    [evidences, chapterId, onViewEvidence],
  )

  return (
    <div className="space-y-4">
      <div
        className="h-[60vh] rounded-md border border-border-subtle bg-bg-card"
        data-testid="kg-review-canvas"
      >
        <GraphCanvas
          layout={layout}
          onNodeClick={handleNodeClick}
          assetId={assetId}
          chapterId={chapterId}
        />
      </div>
      <ReviewerNodeTable layout={layout} />
    </div>
  )
}

interface ApprovalStateBadgeProps {
  state: 'pending' | 'approved' | 'rejected'
}

function ApprovalStateBadge({ state }: ApprovalStateBadgeProps) {
  const map = {
    pending: { label: '待审批', cls: 'bg-warning-bg text-warning' },
    approved: { label: '已通过', cls: 'bg-success-bg text-success-dark' },
    rejected: { label: '已退回', cls: 'bg-danger-bg text-danger' },
  } as const
  const { label, cls } = map[state]
  return (
    <span className={`rounded-full px-2 py-0.5 font-ui text-micro ${cls}`}>
      {label}
    </span>
  )
}
