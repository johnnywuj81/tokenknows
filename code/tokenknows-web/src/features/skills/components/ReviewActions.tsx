/**
 * ReviewActions · v0.6.0 T58 Skill 详情页审批操作.
 *
 * 4 种渲染分支:
 * - status=draft + review_state=not_submitted → "提交审批" 按钮 (作者可见)
 * - review_state=pending_review → "批准 / 退回" 按钮 (reviewer 可见)
 * - review_state=approved → "✅ 已批准 by X" badge
 * - review_state=rejected → "❌ 已退回 by X" badge + 退回理由 + "重新提交" 按钮
 *
 * MVP 不区分 author/reviewer 角色 (生产应换为 project_owner / reviewer role);
 * 当前用户 ∈ contributors 时认作 "可操作".
 */

import { useEffect, useState } from 'react'
import type { Skill } from '@/types/api'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { ReviewDialog } from './ReviewDialog'

interface ReviewActionsProps {
  skill: Skill
}

export function ReviewActions({ skill }: ReviewActionsProps) {
  const user = useAuthStore((s) => s.user)
  const [action, setAction] = useState<
    'submit' | 'approve' | 'reject' | 'resubmit' | null
  >(null)
  // v1.0.1 review fix: skill 变化时重置 action 避免上一个 skill 的 dialog 继续显示
  useEffect(() => {
    setAction(null)
  }, [skill.id])

  const currentUserId = user?.id ?? ''
  // MVP: 任何 contributor 都可以是 reviewer / author
  const isContributor = skill.contributors.includes(currentUserId)

  const latestRecord = skill.review_history.at(-1) ?? null

  // ─── 不可见 (无 review 流程的 skill) ───────────────────
  if (
    skill.review_state === 'not_submitted' &&
    skill.status !== 'draft'
  ) {
    return null
  }

  return (
    <div
      className="rounded-md border border-border-subtle bg-bg-canvas p-4"
      data-testid="review-actions"
    >
      {/* draft + not_submitted → 提交审批 */}
      {skill.status === 'draft' && skill.review_state === 'not_submitted' && (
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-ui text-sm font-medium text-text-primary">
              📝 草稿待审批
            </p>
            <p className="mt-0.5 text-xs text-text-secondary">
              准备好后提交给 Reviewer 审批, 通过后自动转 active 状态.
            </p>
          </div>
          {isContributor && (
            <Button
              variant="default"
              size="sm"
              onClick={() => setAction('submit')}
              data-testid="review-submit-btn"
            >
              提交审批
            </Button>
          )}
        </div>
      )}

      {/* pending_review → reviewer 操作 */}
      {skill.review_state === 'pending_review' && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-ui text-sm font-medium text-warning-dark">
              ⏳ 待审批中
            </p>
            <p className="mt-0.5 text-xs text-text-secondary">
              {latestRecord?.reviewer_id ?? '?'} 提交于{' '}
              {latestRecord
                ? new Date(latestRecord.timestamp).toLocaleString('zh-CN')
                : '—'}
            </p>
          </div>
          {isContributor && (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={() => setAction('approve')}
                data-testid="review-approve-btn"
              >
                ✅ 批准
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAction('reject')}
                data-testid="review-reject-btn"
              >
                ❌ 退回
              </Button>
            </div>
          )}
        </div>
      )}

      {/* approved → badge */}
      {skill.review_state === 'approved' && (
        <div className="flex items-center gap-2">
          <span className="rounded bg-success-bg px-2 py-0.5 font-ui text-xs font-medium text-success-dark">
            ✅ 已批准
          </span>
          <span className="font-mono text-xs text-text-tertiary">
            by {skill.last_reviewer_id} ·{' '}
            {skill.last_reviewed_at
              ? new Date(skill.last_reviewed_at).toLocaleDateString('zh-CN')
              : ''}
          </span>
        </div>
      )}

      {/* rejected → badge + reason + 重新提交 */}
      {skill.review_state === 'rejected' && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="rounded bg-danger-bg px-2 py-0.5 font-ui text-xs font-medium text-danger">
              ❌ 已退回
            </span>
            <span className="font-mono text-xs text-text-tertiary">
              by {skill.last_reviewer_id} ·{' '}
              {skill.last_reviewed_at
                ? new Date(skill.last_reviewed_at).toLocaleDateString('zh-CN')
                : ''}
            </span>
          </div>
          {latestRecord?.note && (
            <p
              className="text-xs text-text-secondary"
              data-testid="review-reject-reason"
            >
              理由: {latestRecord.note}
            </p>
          )}
          {isContributor && (
            <div>
              <Button
                variant="default"
                size="sm"
                onClick={() => setAction('resubmit')}
                data-testid="review-resubmit-btn"
              >
                修订后重新提交
              </Button>
            </div>
          )}
        </div>
      )}

      {action && (
        <ReviewDialog
          skill={skill}
          action={action === 'resubmit' ? 'submit' : action}
          userId={currentUserId}
          onClose={() => setAction(null)}
        />
      )}
    </div>
  )
}
