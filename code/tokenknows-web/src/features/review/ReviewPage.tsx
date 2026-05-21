/**
 * T09 · ReviewPage (Reviewer 审批视图)
 *
 * 三栏:
 *   [左] DocOutline (复用 T06)
 *   [中] 只读 ChapterBlock 列表 (复用 T06 + readOnly)
 *   [右] ApprovalSidebar - 章节级审批进度 + 通过/退回操作
 *
 * 底部固定: BottomActionBar (全部通过 → 跳 T11 / 退回作者 → 回 T06 / 保存进度)
 *
 * 设计依据: 任务包 T09 §4-§8
 */

import { useCallback, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useAsset } from '../documents/hooks/useAsset'
import { useChapters } from '../documents/hooks/useChapters'
import { DocOutline } from '../documents/page/components/DocOutline'
import { ChapterBlock } from '../documents/page/components/ChapterBlock'
import { EvidenceDrawer } from '../documents/page/components/EvidenceDrawer'
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
            onClick={() => projectId && navigate(`/projects/${projectId}/documents/${docId}`)}
            className="font-ui text-caption text-text-muted hover:text-text-primary"
          >
            ← 返回文档
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
          // T11 发布入口待接, 暂时返回文档列表
          if (projectId) navigate(`/projects/${projectId}/documents`)
        }}
      />

      {/* T07 证据抽屉 (审批视角也允许打开看引用) */}
      <EvidenceDrawer assetId={docId} />
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
