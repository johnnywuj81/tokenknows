/**
 * EvidenceDrawer · T07 · 证据链抽屉
 *
 * 入口: 用户点击章节内 [N] 角标 / ChapterFooter "查看证据" 按钮.
 *
 * 数据策略:
 *   - 一次性 fetch 本章节全部证据 (3-4 条)
 *   - 切换 evidence 仅 setActiveEvidence(id), 不重 query
 *   - 抽屉关闭后保留 cache 60s (staleTime)
 *
 * 设计依据: T07 任务包 §3 + SharedFoundations §5 (queryKey 规范).
 */

import { useEffect } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { BookText, Loader2, AlertCircle, FileX } from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useChapterEvidence } from '../../hooks/useChapterEvidence'
import { EvidenceSourceCard } from './EvidenceSourceCard'
import { cn } from '@/lib/utils'

interface EvidenceDrawerProps {
  /** Asset id - 由 DocumentPage 通过 useParams 传入. */
  assetId: string | null | undefined
}

export function EvidenceDrawer({ assetId }: EvidenceDrawerProps) {
  const open = useDocumentUiStore((s) => s.evidenceOpen)
  const chapterId = useDocumentUiStore((s) => s.evidenceChapterId)
  const activeId = useDocumentUiStore((s) => s.activeEvidenceId)
  const setActive = useDocumentUiStore((s) => s.setActiveEvidence)
  const close = useDocumentUiStore((s) => s.closeEvidence)

  const query = useChapterEvidence(assetId, open ? chapterId : null)
  const evidenceList = query.data

  // 列表加载完后: 如果没指定 activeId / activeId 不在列表里 → 默认聚焦第 1 条.
  // 直接依赖 query.data (TanStack Query 缓存稳定引用), 不会每渲染都触发.
  useEffect(() => {
    if (!open || !evidenceList || evidenceList.length === 0) return
    const isInList = activeId && evidenceList.some((e) => e.id === activeId)
    if (!isInList) {
      setActive(evidenceList[0].id)
    }
  }, [open, evidenceList, activeId, setActive])

  const list = evidenceList ?? []
  const activeEvidence = list.find((e) => e.id === activeId) ?? list[0] ?? null

  return (
    <Sheet open={open} onOpenChange={(o) => !o && close()}>
      <SheetContent
        side="right"
        className="flex w-[480px] flex-col gap-0 p-0 sm:max-w-[480px]"
      >
        <SheetHeader className="border-b border-border-subtle px-6 py-4">
          <SheetTitle className="flex items-center gap-2 font-content text-h3">
            <BookText className="size-4" />
            证据链
            {list.length > 0 ? (
              <span className="ml-1 font-mono text-caption text-text-subtle">
                ({list.length} 条)
              </span>
            ) : null}
          </SheetTitle>
          <SheetDescription className="font-ui text-caption text-text-muted">
            本章节内引用的研发事件原文. 点击编号切换查看.
          </SheetDescription>
        </SheetHeader>

        {/* Tab 条 - 数字索引 */}
        {list.length > 0 ? (
          <nav
            className="flex items-center gap-1 overflow-x-auto border-b border-border-subtle bg-bg-card px-6 py-3"
            aria-label="证据编号"
          >
            {list.map((ev, idx) => {
              const isActive = activeEvidence?.id === ev.id
              return (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => setActive(ev.id)}
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full font-mono text-caption transition',
                    isActive
                      ? 'bg-accent-primary text-inverse-text shadow-sm'
                      : 'border border-border-subtle bg-bg-card text-text-secondary hover:bg-bg-warm',
                  )}
                  aria-label={`查看证据 ${idx + 1}`}
                  aria-pressed={isActive}
                >
                  {idx + 1}
                </button>
              )
            })}
          </nav>
        ) : null}

        {/* 主体 · 三态 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {query.isLoading ? (
            <DrawerLoading />
          ) : query.error ? (
            <DrawerError onRetry={() => query.refetch()} />
          ) : list.length === 0 ? (
            <DrawerEmpty />
          ) : activeEvidence ? (
            <EvidenceSourceCard evidence={activeEvidence} />
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function DrawerLoading() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
      <Loader2 className="size-5 animate-spin" />
      <p className="font-ui text-caption">加载证据中…</p>
    </div>
  )
}

function DrawerError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-muted">
      <AlertCircle className="size-5 text-danger" />
      <p className="font-ui text-body-sm">证据加载失败</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md border border-border-subtle bg-bg-card px-3 py-1.5 font-ui text-caption text-accent-primary-dark transition hover:bg-bg-warm"
      >
        重试
      </button>
    </div>
  )
}

function DrawerEmpty() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
      <FileX className="size-5" />
      <p className="font-ui text-body-sm">本章节暂无证据引用</p>
      <p className="font-ui text-caption text-text-subtle">
        重生成或手动添加引用后会出现在这里
      </p>
    </div>
  )
}
