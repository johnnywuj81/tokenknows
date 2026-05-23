/**
 * ConsentPending · Skill 详情页顶部 banner (v0.5.1 T51).
 *
 * 显示条件: skill.status === 'pending_contributor_consent'
 * 当前用户 ∈ consent_required_from 时显示 [同意 / 拒绝] 按钮.
 *
 * 状态机:
 * - 待签人数 = required_count - signed_count
 * - 截止时间 = consent_expires_at
 * - 当前用户已签 → 显示 "你已同意 · 等待 N 位 contributor"
 *
 * 设计依据: T51 §5.
 */

import { useState } from 'react'
import type { Skill } from '@/types/api'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { ConsentDialog } from './ConsentDialog'

interface ConsentPendingProps {
  skill: Skill
}

export function ConsentPending({ skill }: ConsentPendingProps) {
  const user = useAuthStore((s) => s.user)
  const [action, setAction] = useState<'sign' | 'reject' | null>(null)

  // 仅 pending 时显示
  if (skill.status !== 'pending_contributor_consent') {
    return null
  }

  const required = skill.consent_required_from
  const signedIds = skill.consent_signed_by.map((r) => r.user_id)
  const signedCount = signedIds.length
  const requiredCount = required.length
  const waiting = requiredCount - signedCount

  // 当前用户身份 (MVP: 用 user.id 当 platform user_id);
  // 生产应通过 IM 映射 (user.im_user_id) 拿到对应 platform id.
  const currentUserId = user?.id ?? ''
  const isContributor = required.includes(currentUserId)
  const hasSigned = signedIds.includes(currentUserId)

  const expiresLabel = skill.consent_expires_at
    ? new Date(skill.consent_expires_at).toLocaleDateString('zh-CN')
    : '—'

  return (
    <div
      className="rounded-md border border-warning bg-warning-bg p-4"
      data-testid="consent-pending-banner"
      role="region"
      aria-label="Skill 等待 contributor 同意"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex-1">
          <p className="font-content text-base font-medium text-warning-dark">
            🟡 等待 contributor 同意发布
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            还差 {waiting}/{requiredCount} contributor 签字 · 截止 {expiresLabel}
          </p>
          {hasSigned && (
            <p className="mt-1 text-xs text-success-dark">
              ✓ 你已同意, 等待其他 {waiting} 位 contributor 签字
            </p>
          )}
        </div>

        {isContributor && !hasSigned && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="default"
              size="sm"
              onClick={() => setAction('sign')}
              data-testid="consent-sign-btn"
            >
              👍 同意发布
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAction('reject')}
              data-testid="consent-reject-btn"
            >
              👎 拒绝
            </Button>
          </div>
        )}
      </div>

      {action && (
        <ConsentDialog
          skill={skill}
          action={action}
          userId={currentUserId}
          onClose={() => setAction(null)}
        />
      )}
    </div>
  )
}
