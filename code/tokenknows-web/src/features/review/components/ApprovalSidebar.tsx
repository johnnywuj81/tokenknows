/**
 * ApprovalSidebar · T09 右侧审批进度
 *
 * 每章一行: 标题 + 状态 badge + 通过 / 退回 操作.
 * 退回弹 Dialog 输入 reason.
 */

import { useState } from 'react'
import { CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import type { Chapter } from '@/types/api'
import { useApproveChapter, useRejectChapter } from '../hooks/useReviewMutations'
import { cn } from '@/lib/utils'

interface ApprovalSidebarProps {
  assetId: string
  chapters: Chapter[]
  highlightChapterId?: string | null
  onScrollToChapter: (id: string) => void
}

export function ApprovalSidebar({
  assetId,
  chapters,
  highlightChapterId,
  onScrollToChapter,
}: ApprovalSidebarProps) {
  const approve = useApproveChapter()
  const reject = useRejectChapter()
  const [rejectTarget, setRejectTarget] = useState<Chapter | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  function handleApprove(chapter: Chapter) {
    approve.mutate({ assetId, chapterId: chapter.id })
  }

  function handleRejectSubmit() {
    if (!rejectTarget) return
    const trimmed = rejectReason.trim()
    if (trimmed.length < 3) return
    reject.mutate(
      { assetId, chapterId: rejectTarget.id, reason: trimmed },
      {
        onSuccess: () => {
          setRejectTarget(null)
          setRejectReason('')
        },
      },
    )
  }

  return (
    <aside
      className="flex h-full min-h-0 flex-col gap-3 overflow-auto border-l border-border-subtle bg-bg-card p-4"
      aria-label="审批进度"
    >
      <header>
        <h2 className="font-content text-h3 text-text-primary">章节审批</h2>
        <p className="font-ui text-caption text-text-muted">
          逐章通过 / 退回. 任一退回, 文档整体退回作者.
        </p>
      </header>

      <ul className="space-y-2">
        {chapters.map((ch, idx) => {
          const isPending =
            (approve.isPending && approve.variables?.chapterId === ch.id) ||
            (reject.isPending && reject.variables?.chapterId === ch.id)

          return (
            <li
              key={ch.id}
              className={cn(
                'rounded-md border bg-bg-card p-3 transition',
                ch.approval_state === 'approved'
                  ? 'border-success-border bg-success-bg/30'
                  : ch.approval_state === 'rejected'
                    ? 'border-danger-border bg-danger-bg/30'
                    : 'border-border-subtle',
                highlightChapterId === ch.id ? 'ring-2 ring-accent-primary' : '',
              )}
            >
              <button
                type="button"
                onClick={() => onScrollToChapter(ch.id)}
                className="block w-full text-left"
              >
                <span className="font-mono text-micro text-text-subtle">§{idx + 1}</span>
                <span className="ml-1 font-content text-body-sm text-text-primary">
                  {ch.title}
                </span>
              </button>

              <StateBadge state={ch.approval_state} />

              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={ch.approval_state === 'approved' ? 'outline' : 'default'}
                  disabled={isPending || ch.approval_state === 'approved'}
                  onClick={() => handleApprove(ch)}
                  className="flex-1 font-ui text-caption"
                >
                  {approve.isPending && approve.variables?.chapterId === ch.id ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <CheckCircle2 className="size-3" />
                  )}
                  通过
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={isPending}
                  onClick={() => {
                    setRejectTarget(ch)
                    setRejectReason('')
                  }}
                  className="flex-1 font-ui text-caption text-danger hover:bg-danger-bg/40"
                >
                  <XCircle className="size-3" />
                  退回
                </Button>
              </div>
            </li>
          )
        })}
      </ul>

      {/* 退回 Dialog */}
      <Dialog
        open={rejectTarget !== null}
        onOpenChange={(o) => {
          if (!o && !reject.isPending) {
            setRejectTarget(null)
            setRejectReason('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-content">
              <XCircle className="size-4 text-danger" />
              退回章节
            </DialogTitle>
            <DialogDescription className="font-ui text-caption text-text-muted">
              {rejectTarget ? `章节: §${rejectTarget.order_index + 1} ${rejectTarget.title}` : ''}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <label
              htmlFor="reject-reason"
              className="font-ui text-caption font-medium text-text-secondary"
            >
              退回原因 <span className="text-danger">*</span>
            </label>
            <textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              disabled={reject.isPending}
              placeholder="说明本章节需要作者怎样调整 (≥3 字符)"
              rows={4}
              className="w-full resize-none rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary placeholder:text-text-subtle focus:border-accent-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
            <p className="font-ui text-micro text-text-subtle">
              至少 3 个字符. 当前 {rejectReason.trim().length} 字符.
            </p>
            {reject.error ? (
              <div className="flex items-start gap-1.5 rounded-md border border-danger-border bg-danger-bg px-2 py-1.5 text-danger">
                <AlertCircle className="size-3.5 mt-0.5 shrink-0" />
                <p className="font-ui text-caption">退回失败, 请重试.</p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={reject.isPending}
              onClick={() => {
                setRejectTarget(null)
                setRejectReason('')
              }}
              className="font-ui"
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={reject.isPending || rejectReason.trim().length < 3}
              onClick={handleRejectSubmit}
              className="font-ui"
            >
              {reject.isPending ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  退回中…
                </>
              ) : (
                <>
                  <XCircle className="size-3.5" />
                  确认退回
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  )
}

interface StateBadgeProps {
  state: Chapter['approval_state']
}

function StateBadge({ state }: StateBadgeProps) {
  const map = {
    pending: { label: '待审批', cls: 'bg-bg-warm text-text-muted' },
    approved: { label: '已通过', cls: 'bg-success-bg text-success-dark' },
    rejected: { label: '已退回', cls: 'bg-danger-bg text-danger' },
  } as const
  const { label, cls } = map[state]
  return (
    <span
      className={cn('mt-1 inline-block rounded-full px-2 py-0.5 font-ui text-micro', cls)}
    >
      {label}
    </span>
  )
}
