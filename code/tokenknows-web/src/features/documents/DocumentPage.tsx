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
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useSubmitAsset } from '../review/hooks/useReviewMutations'
import { useAsset } from './hooks/useAsset'
import { useChapters } from './hooks/useChapters'
import { DocHeader } from './page/components/DocHeader'
import { DocOutline } from './page/components/DocOutline'
import { ChapterBlock } from './page/components/ChapterBlock'
import { DocSidebar } from './page/components/DocSidebar'
import { EvidenceDrawer } from './page/components/EvidenceDrawer'
import { RegenerateDialog } from './page/components/RegenerateDialog'
import { PublishDialog } from '../publish/PublishDialog'

export default function DocumentPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>()
  const navigate = useNavigate()
  const assetQuery = useAsset(docId)
  const chaptersQuery = useChapters(docId)
  const scrollRef = useRef<HTMLDivElement>(null)

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

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <DocHeader
        asset={asset}
        onSubmit={handleSubmitForReview}
        submitting={submitMutation.isPending}
        onPublish={openPublish}
      />

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
