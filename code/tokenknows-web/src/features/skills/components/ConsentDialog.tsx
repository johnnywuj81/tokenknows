/**
 * ConsentDialog · 二次确认弹窗 (v0.5.1 T51).
 *
 * 流程:
 *   - sign: 1 个 confirm 即可 (低 friction)
 *   - reject: 必填 reason ≥ 5 字符, 否则 confirm 按钮 disabled
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
import { useRejectConsent, useSignConsent } from '../hooks/useSkills'

interface ConsentDialogProps {
  skill: Skill
  action: 'sign' | 'reject'
  userId: string
  onClose: () => void
}

const REJECT_MIN_LEN = 5

export function ConsentDialog({
  skill,
  action,
  userId,
  onClose,
}: ConsentDialogProps) {
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const sign = useSignConsent(skill.project_id)
  const reject = useRejectConsent(skill.project_id)
  const isMutating = sign.isPending || reject.isPending

  const handleConfirm = async (): Promise<void> => {
    setError(null)
    try {
      if (action === 'sign') {
        await sign.mutateAsync({
          skillId: skill.id,
          body: { user_id: userId, channel: 'web', note: note || undefined },
        })
      } else {
        if (reason.trim().length < REJECT_MIN_LEN) {
          setError(`理由至少 ${REJECT_MIN_LEN} 个字符`)
          return
        }
        await reject.mutateAsync({
          skillId: skill.id,
          body: { user_id: userId, channel: 'web', reason: reason.trim() },
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

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="consent-dialog">
        <DialogHeader>
          <DialogTitle>
            {isReject ? '拒绝发布该 Skill' : '同意发布该 Skill'}
          </DialogTitle>
          <DialogDescription>
            {isReject
              ? '请填写拒绝理由 (≥ 5 字), 用于审计 + SignalGate 调权.'
              : '同意后该 Skill 将进入 draft 待审批阶段 (Reviewer 流程).'}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <p className="text-sm text-text-secondary">
            <strong className="font-medium text-text-primary">
              {skill.name}
            </strong>
          </p>

          {isReject ? (
            <>
              <label
                htmlFor="reject-reason"
                className="font-ui text-sm font-medium text-text-secondary"
              >
                拒绝理由 (必填, ≥ {REJECT_MIN_LEN} 字)
              </label>
              <Textarea
                id="reject-reason"
                data-testid="reject-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="例如: 此聊天属于 HR 私下讨论, 不宜蒸馏为项目知识"
                rows={4}
                maxLength={500}
              />
              <p className="text-right text-xs text-text-tertiary">
                {reason.length} / 500
              </p>
            </>
          ) : (
            <>
              <label
                htmlFor="sign-note"
                className="font-ui text-sm font-medium text-text-secondary"
              >
                备注 (可选)
              </label>
              <Textarea
                id="sign-note"
                data-testid="sign-note-input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="对该 Skill 的说明 / 适用范围 (≤ 200 字)"
                rows={3}
                maxLength={200}
              />
            </>
          )}

          {error && (
            <p
              className="text-sm text-danger"
              data-testid="consent-dialog-error"
            >
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isMutating}
          >
            取消
          </Button>
          <Button
            variant={isReject ? 'destructive' : 'default'}
            onClick={handleConfirm}
            disabled={!canSubmit || isMutating}
            data-testid="consent-dialog-confirm"
          >
            {isMutating ? '提交中…' : isReject ? '确认拒绝' : '确认同意'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
