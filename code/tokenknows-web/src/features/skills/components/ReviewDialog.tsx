/**
 * ReviewDialog · v0.6.0 T58 二次确认弹窗 (submit / approve / reject).
 *
 * - submit / approve: 1 个 confirm; note 可选
 * - reject: 必填 reason ≥ 5 字符, 否则 confirm disabled
 */

import { useState } from 'react'
import type { Skill } from '@/types/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import {
  useApproveSkillReview,
  useRejectSkillReview,
  useSubmitSkillForReview,
} from '../hooks/useSkills'

interface ReviewDialogProps {
  skill: Skill
  action: 'submit' | 'approve' | 'reject'
  userId: string
  onClose: () => void
}

const REJECT_MIN_LEN = 5
const NOTE_MAX = 300
const REASON_MAX = 500

export function ReviewDialog({
  skill,
  action,
  userId,
  onClose,
}: ReviewDialogProps) {
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = useSubmitSkillForReview(skill.project_id)
  const approve = useApproveSkillReview(skill.project_id)
  const reject = useRejectSkillReview(skill.project_id)
  const isMutating =
    submit.isPending || approve.isPending || reject.isPending

  const titleMap = {
    submit: '提交审批',
    approve: '批准发布',
    reject: '退回 Skill',
  }
  const descMap = {
    submit: '提交后 Reviewer 将收到通知; 通过后 Skill 自动转 active 状态.',
    approve: '批准后 Skill 立刻进入 active, 可被下游生成注入.',
    reject: '请填写退回理由 (≥ 5 字), 作者收到通知后可修订重提.',
  }

  async function handleConfirm(): Promise<void> {
    setError(null)
    try {
      if (action === 'submit') {
        await submit.mutateAsync({
          skillId: skill.id,
          body: { user_id: userId, note: note || undefined },
        })
      } else if (action === 'approve') {
        await approve.mutateAsync({
          skillId: skill.id,
          body: { reviewer_id: userId, note: note || undefined },
        })
      } else {
        if (reason.trim().length < REJECT_MIN_LEN) {
          setError(`理由至少 ${REJECT_MIN_LEN} 个字符`)
          return
        }
        await reject.mutateAsync({
          skillId: skill.id,
          body: { reviewer_id: userId, reason: reason.trim() },
        })
      }
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '操作失败, 请重试')
    }
  }

  const isReject = action === 'reject'
  const canSubmit = isReject
    ? reason.trim().length >= REJECT_MIN_LEN
    : true

  const confirmVariant =
    action === 'reject' ? 'destructive' : 'default'

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="review-dialog">
        <DialogHeader>
          <DialogTitle>{titleMap[action]} · {skill.name}</DialogTitle>
          <DialogDescription>{descMap[action]}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {isReject ? (
            <>
              <label
                htmlFor="reject-reason"
                className="font-ui text-sm font-medium text-text-secondary"
              >
                退回理由 (必填, ≥ {REJECT_MIN_LEN} 字)
              </label>
              <Textarea
                id="reject-reason"
                data-testid="review-reject-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="例如: 需要更具体的示例步骤, 当前内容过于通用."
                rows={4}
                maxLength={REASON_MAX}
              />
              <p className="text-right text-xs text-text-tertiary">
                {reason.length} / {REASON_MAX}
              </p>
            </>
          ) : (
            <>
              <label
                htmlFor="review-note"
                className="font-ui text-sm font-medium text-text-secondary"
              >
                备注 (可选)
              </label>
              <Textarea
                id="review-note"
                data-testid="review-note-input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={
                  action === 'submit'
                    ? '给 Reviewer 的说明 / 适用范围'
                    : '批准意见 (将记录到审批历史)'
                }
                rows={3}
                maxLength={NOTE_MAX}
              />
            </>
          )}

          {error && (
            <p
              className="text-sm text-danger"
              data-testid="review-dialog-error"
            >
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isMutating}>
            取消
          </Button>
          <Button
            variant={confirmVariant}
            onClick={handleConfirm}
            disabled={!canSubmit || isMutating}
            data-testid="review-dialog-confirm"
          >
            {isMutating ? '提交中…' : `确认${titleMap[action]}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
