/**
 * T06 · DocumentPage (文档生成结果页 · 产品核心卖点屏)
 *
 * 三栏: 左 240 大纲 / 中自适应正文 / 右 320 侧栏
 *
 * Phase 1: 三栏布局 + markdown-it 静态渲染 + 大纲滚动联动 + 自评卡
 * Phase 2: TipTap + 自动保存 (debounce 2s)
 * Phase 3 (本提交): InlineEvidence 角标 + T07/T08 stub Drawer/Dialog 接入
 */

import { useCallback, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import type { Asset, Chapter } from '@/types/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useSubmitAsset } from '../review/hooks/useReviewMutations'
import { useAsset } from './hooks/useAsset'
import { useChapters } from './hooks/useChapters'
import { useGenerationSSE } from './hooks/useGenerationSSE'
import { DocHeader } from './page/components/DocHeader'
import { DocOutline } from './page/components/DocOutline'
import { ChapterBlock } from './page/components/ChapterBlock'
import { DocSidebar } from './page/components/DocSidebar'
import { EvidenceDrawer } from './page/components/EvidenceDrawer'
import { RegenerateDialog } from './page/components/RegenerateDialog'
import { BookProgressCard } from './page/components/BookProgressCard'
import { KnowledgeGraphView } from './knowledge-graph/KnowledgeGraphView'
import { PublishDialog } from '../publish/PublishDialog'

export default function DocumentPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>()
  const navigate = useNavigate()
  const assetQuery = useAsset(docId)
  const chaptersQuery = useChapters(docId)
  const scrollRef = useRef<HTMLDivElement>(null)

  // P4 · 文档生成中订阅 SSE, 替代 polling. status=generating 时开,
  // 收到 done/failed 自动关. chapter_completed 事件 invalidate chapters
  // → ChapterBlock 增量出现.
  useGenerationSSE({
    assetId: docId,
    enabled: assetQuery.data?.status === 'generating',
  })

  const openEvidence = useDocumentUiStore((s) => s.openEvidence)
  const openRegenerate = useDocumentUiStore((s) => s.openRegenerate)
  const regenerateChapterId = useDocumentUiStore((s) => s.regenerateChapterId)
  const regenerateOpen = useDocumentUiStore((s) => s.regenerateOpen)
  const openPublish = useDocumentUiStore((s) => s.openPublish)

  const handleViewEvidence = useCallback(
    (chapterId: string, evidenceId?: string) => {
      // 没指定 evidenceId 时 (来自 footer "查看证据" 按钮) → EvidenceDrawer 内
      // useEffect 会读 evidence 列表后默认聚焦第 1 条.
      openEvidence(chapterId, evidenceId ?? null)
    },
    [openEvidence],
  )

  const handleRegenerate = useCallback(
    (chapterId: string) => {
      openRegenerate(chapterId)
    },
    [openRegenerate],
  )

  const submitMutation = useSubmitAsset()
  const handleSubmitForReview = useCallback(() => {
    if (!projectId || !docId) return
    submitMutation.mutate(docId, {
      onSuccess: () => {
        navigate(`/projects/${projectId}/documents/${docId}/review`)
      },
    })
  }, [projectId, docId, navigate, submitMutation])

  const isLoading = assetQuery.isLoading || chaptersQuery.isLoading
  const error = assetQuery.error ?? chaptersQuery.error

  if (error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="文档加载失败"
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

  // v1.2 · knowledge_graph 分支: 复用 DocHeader, 中部换成 GraphCanvas
  // v1.2.1 T88: 抽出子组件 KnowledgeGraphView 以便 useChapterEvidence (hook
  //              不能在条件分支里直接调).
  if (asset.type === 'knowledge_graph' && chapters.length > 0) {
    return (
      <KnowledgeGraphView
        asset={asset}
        chapter={chapters[0]}
        onSubmit={handleSubmitForReview}
        submitting={submitMutation.isPending}
        onPublish={openPublish}
        onOpenEvidence={handleViewEvidence}
      />
    )
  }

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <DocHeader
        asset={asset}
        onSubmit={handleSubmitForReview}
        submitting={submitMutation.isPending}
        onPublish={openPublish}
      />

      {/* v0.2 · book 类型生成中显示卷/章计数 + 预计剩余 */}
      {asset.type === 'book' && docId && (
        <BookProgressCard
          assetId={docId}
          enabled={asset.status === 'generating'}
        />
      )}

      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)_320px]">
        {/* 左 · 大纲 */}
        <DocOutline chapters={chapters} scrollRef={scrollRef} />

        {/* 中 · 正文 (滚动容器) */}
        <main
          ref={scrollRef}
          className="overflow-auto bg-bg-page px-6 py-6"
          aria-label="文档正文"
        >
          {chapters.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border-medium bg-bg-card p-8 text-center">
              <p className="font-content text-h3 text-text-primary">章节尚未生成</p>
              <p className="mt-2 text-body text-text-muted">
                文档当前状态: <strong>{asset.status}</strong>. 流水线完成后章节会自动出现。
              </p>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {/* T128 · 整 asset 被退回时显示顶部 banner + 跳第一章按钮 */}
              <AssetRejectedBanner asset={asset} chapters={chapters} />
              {chapters.map((ch) => (
                <ChapterBlock
                  key={ch.id}
                  chapter={ch}
                  regenerating={regenerateOpen && regenerateChapterId === ch.id}
                  onViewEvidence={handleViewEvidence}
                  onRegenerate={handleRegenerate}
                />
              ))}
            </div>
          )}
        </main>

        {/* 右 · 侧栏 */}
        <DocSidebar asset={asset} />
      </div>

      {/* T07 · 证据链抽屉 */}
      <EvidenceDrawer assetId={docId} />

      {/* T08 · 重生成对话框 */}
      <RegenerateDialog assetId={docId} />

      {/* T11 · 发布对话框 */}
      <PublishDialog assetId={docId} />
    </div>
  )
}


// ── T128 · 整 asset 退回顶部 banner ─────────────────────────────


interface AssetRejectedBannerProps {
  asset: Asset
  chapters: Chapter[]
}


/**
 * 当 asset.approval_state='rejected' 时显示在文档顶部, 提示作者审批人退回了
 * 整个文档, 提供"跳到第一个被退回章节"操作.
 *
 * 与 ChapterBlock 的 RejectReasonBanner 互补: 这里是全局摘要 (N 章被退回),
 * 章节内部 banner 显示每章的具体理由.
 */
function AssetRejectedBanner({ asset, chapters }: AssetRejectedBannerProps) {
  if (asset.approval_state !== 'rejected') return null
  const rejectedChapters = chapters.filter((c) => c.approval_state === 'rejected')
  if (rejectedChapters.length === 0) {
    // asset.approval_state=rejected 但章节都已修订过 — 仍提示一下全局状态
    return (
      <div
        role="alert"
        data-testid="asset-rejected-banner"
        className="flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg/30 px-4 py-3"
      >
        <XCircle className="size-5 shrink-0 text-danger mt-0.5" />
        <div className="flex-1">
          <p className="font-content text-h3 text-danger-dark">本文档之前被退回</p>
          <p className="mt-1 font-ui text-body-sm text-text-secondary">
            修订完成后请重新提交审批。
          </p>
        </div>
      </div>
    )
  }
  const firstRejected = rejectedChapters[0]
  function scrollToFirstRejected(): void {
    const el = document.getElementById(`chapter-anchor-${firstRejected.id}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <div
      role="alert"
      data-testid="asset-rejected-banner"
      className="flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg/30 px-4 py-3"
    >
      <XCircle className="size-5 shrink-0 text-danger mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="font-content text-h3 text-danger-dark">
          审批人退回了 {rejectedChapters.length} 个章节
        </p>
        <p className="mt-1 font-ui text-body-sm text-text-secondary">
          每个被退回章节下方有审批人填写的理由。修订完成后请用顶部「提交审批」重新发起。
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={scrollToFirstRejected}
          >
            跳到第一个退回章节 (§{firstRejected.order_index + 1})
          </Button>
          <span className="font-mono text-caption text-text-muted">
            退回章节: {rejectedChapters.map((c) => `§${c.order_index + 1}`).join(' · ')}
          </span>
        </div>
      </div>
    </div>
  )
}
