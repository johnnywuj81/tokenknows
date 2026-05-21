/**
 * T06 · DocumentPage (文档生成结果页 · 产品核心卖点屏)
 *
 * 三栏: 左 240 大纲 / 中自适应正文 / 右 320 侧栏
 *
 * Phase 1 (本提交): 三栏布局 + markdown-it 静态渲染 + 大纲滚动联动 + 自评卡
 * Phase 2 (后续): TipTap + 自动保存
 * Phase 3 (后续): InlineEvidence 角标 + T07/T08 抽屉/对话框接入
 */

import { useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { useAsset } from './hooks/useAsset'
import { useChapters } from './hooks/useChapters'
import { DocHeader } from './page/components/DocHeader'
import { DocOutline } from './page/components/DocOutline'
import { ChapterBlock } from './page/components/ChapterBlock'
import { DocSidebar } from './page/components/DocSidebar'

export default function DocumentPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>()
  const navigate = useNavigate()
  const assetQuery = useAsset(docId)
  const chaptersQuery = useChapters(docId)
  const scrollRef = useRef<HTMLDivElement>(null)

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
      <DocHeader asset={asset} />

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
                <ChapterBlock key={ch.id} chapter={ch} />
              ))}
            </div>
          )}
        </main>

        {/* 右 · 侧栏 */}
        <DocSidebar asset={asset} />
      </div>
    </div>
  )
}
