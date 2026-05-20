/**
 * T05 · DocumentListPage
 *
 * 文档列表 + 筛选 + 生成 + 克隆 + 删除二次确认
 *
 * 决策依据 TaskTechDesign T05 + tasks/T05-document-list.md
 */

import { useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Loader2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { Skeleton } from '@/components/ui/skeleton'
import { useAssets } from './hooks/useAssets'
import { useDeleteAsset } from './hooks/useDeleteAsset'
import { useCloneAsset } from './hooks/useCloneAsset'
import { DocumentCard } from './list/DocumentCard'
import { DocumentFilters } from './list/DocumentFilters'
import { GenerateDocDialog } from './list/GenerateDocDialog'
import type { AssetStatus, AssetType } from '@/types/api'

export default function DocumentListPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const type = (searchParams.get('type') ?? 'all') as AssetType | 'all'
  const status = (searchParams.get('status') ?? 'all') as AssetStatus | 'all'

  const filters = useMemo(
    () => ({
      type: type === 'all' ? undefined : type,
      status: status === 'all' ? undefined : status,
    }),
    [type, status],
  )

  const assetsQuery = useAssets(projectId, filters)
  const deleteAsset = useDeleteAsset()
  const cloneAsset = useCloneAsset()

  const [generateOpen, setGenerateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null)

  const allAssets = useMemo(
    () => (assetsQuery.data?.pages ?? []).flatMap((p) => p.data),
    [assetsQuery.data],
  )

  const updateFilter = (key: 'type' | 'status', value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === 'all') next.delete(key)
    else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  const handleClone = (assetId: string) => {
    if (!projectId) return
    cloneAsset.mutate({ projectId, assetId })
  }

  const confirmDelete = () => {
    if (!projectId || !deleteTarget) return
    deleteAsset.mutate(
      { projectId, assetId: deleteTarget.id },
      { onSuccess: () => setDeleteTarget(null) },
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
            T05 · 文档
          </p>
          <h1 className="font-content text-h1 text-text-primary">项目文档</h1>
          <p className="text-body text-text-muted">
            自动生成的周报 / 技术方案 / ADR / 复盘。点击卡片进入编辑。
          </p>
        </div>
        <Button
          className="font-ui"
          onClick={() => setGenerateOpen(true)}
          disabled={!projectId}
        >
          <Plus className="size-4" />
          生成新文档
        </Button>
      </header>

      <div className="mb-4">
        <DocumentFilters
          type={type}
          status={status}
          onTypeChange={(t) => updateFilter('type', t)}
          onStatusChange={(s) => updateFilter('status', s)}
        />
      </div>

      {assetsQuery.error ? (
        <ErrorState
          variant="fullscreen"
          title="文档列表加载失败"
          error={assetsQuery.error}
          onRetry={() => assetsQuery.refetch()}
        />
      ) : assetsQuery.isLoading ? (
        <LoadingSkeleton variant="list" />
      ) : allAssets.length === 0 ? (
        <EmptyState
          title={type !== 'all' || status !== 'all' ? '该条件下没有文档' : '还没有文档'}
          description={
            type !== 'all' || status !== 'all'
              ? '尝试清除筛选条件,或生成一份新文档。'
              : '接入数据源后,事件累积到阈值即自动生成首份周报。也可手动触发任意类型生成。'
          }
          action={{
            label: '+ 生成第一份',
            onClick: () => setGenerateOpen(true),
          }}
        />
      ) : (
        <>
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {allAssets.map((asset) => (
              <li key={asset.id}>
                <DocumentCard
                  asset={asset}
                  projectId={projectId ?? ''}
                  onClone={handleClone}
                  onDelete={(id, title) => setDeleteTarget({ id, title })}
                />
              </li>
            ))}
            {assetsQuery.isFetchingNextPage
              ? Array.from({ length: 3 }).map((_, i) => (
                  <li key={`skeleton-${i}`}>
                    <div className="space-y-3 rounded-lg border border-border-subtle p-4">
                      <Skeleton className="h-5 w-1/2" />
                      <Skeleton className="h-12 w-full" />
                      <Skeleton className="h-3 w-2/3" />
                    </div>
                  </li>
                ))
              : null}
          </ul>

          {assetsQuery.hasNextPage ? (
            <div className="mt-6 flex justify-center">
              <Button
                variant="outline"
                onClick={() => assetsQuery.fetchNextPage()}
                disabled={assetsQuery.isFetchingNextPage}
                className="font-ui text-caption"
              >
                {assetsQuery.isFetchingNextPage ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    加载中
                  </>
                ) : (
                  '加载更多'
                )}
              </Button>
            </div>
          ) : null}
        </>
      )}

      {projectId ? (
        <GenerateDocDialog
          projectId={projectId}
          open={generateOpen}
          onOpenChange={setGenerateOpen}
        />
      ) : null}

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除文档</DialogTitle>
            <DialogDescription>
              确认删除 <strong className="text-text-primary">{deleteTarget?.title}</strong>?
              删除后不可恢复, 关联的证据链与发布记录会保留但失效。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteAsset.isPending}
              className="font-ui"
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteAsset.isPending}
              className="font-ui"
            >
              {deleteAsset.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  删除中...
                </>
              ) : (
                '确认删除'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
