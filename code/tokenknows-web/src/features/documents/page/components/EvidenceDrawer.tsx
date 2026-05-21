/**
 * EvidenceDrawer · T06 Phase 3 stub (T07 完整实现).
 *
 * 点击章节内 [N] 角标 → 这里展示对应证据的占位.
 * T07 任务包会接真证据数据 (GET /assets/:id/chapters/:chapter_id/evidence).
 */

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { BookText, ExternalLink } from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'

export function EvidenceDrawer() {
  const open = useDocumentUiStore((s) => s.evidenceOpen)
  const activeId = useDocumentUiStore((s) => s.activeEvidenceId)
  const close = useDocumentUiStore((s) => s.closeEvidence)

  return (
    <Sheet open={open} onOpenChange={(o) => !o && close()}>
      <SheetContent side="right" className="w-[480px] sm:max-w-[480px]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 font-content">
            <BookText className="size-4" />
            证据链 (T07 占位)
          </SheetTitle>
          <SheetDescription>
            完整实现待 T07. 这里展示该角标关联的原始 PR / 对话 / commit 占位.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4 px-4">
          <div className="rounded-md border border-border-subtle bg-bg-card p-3">
            <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
              证据 ID
            </p>
            <p className="mt-1 font-mono text-body-sm text-text-primary">
              {activeId ?? '—'}
            </p>
          </div>

          <div className="rounded-md border border-info-border bg-info-bg p-3 text-info">
            <p className="font-ui text-body-sm">
              T07 抽屉完整版会展示:
            </p>
            <ul className="mt-2 space-y-1 font-ui text-caption">
              <li>· 引用的原始 Event (title / source / author / occurred_at)</li>
              <li>· 高亮原文 span 预览</li>
              <li>· trust_score 分项细解</li>
              <li>· "在源头打开" 外链 (GitHub PR / chat link)</li>
              <li>· "标记为 stale" / "删除引用" 操作</li>
            </ul>
          </div>

          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-secondary transition hover:bg-bg-warm"
            onClick={close}
          >
            <ExternalLink className="size-3.5" />
            关闭
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
