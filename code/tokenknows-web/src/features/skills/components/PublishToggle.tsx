/**
 * PublishToggle · v1.0.0 T70 · Skill 发布到 Marketplace 切换.
 *
 * 仅 status=active + review_state=approved 时显示;
 * 仅 owner 操作 (后端 ACL 兜底; 这里 UI 不做 owner 校验, 显示给所有人但点击会 403).
 */

import { useState } from 'react'
import type { Skill } from '@/types/api'
import { Button } from '@/components/ui/button'
import {
  usePublishSkill,
  useUnpublishSkill,
} from '@/features/marketplace/hooks/useMarketplace'

interface PublishToggleProps {
  skill: Skill
}

export function PublishToggle({ skill }: PublishToggleProps) {
  const publish = usePublishSkill(skill.project_id)
  const unpublish = useUnpublishSkill(skill.project_id)
  const [error, setError] = useState<string | null>(null)

  // 不满足条件 → 不渲染 (避免 UI 干扰)
  const canPublish =
    skill.status === 'active' && skill.review_state === 'approved'
  if (!canPublish && skill.visibility !== 'public') {
    return null
  }

  const isPublic = skill.visibility === 'public'

  async function handleToggle(): Promise<void> {
    setError(null)
    try {
      if (isPublic) {
        await unpublish.mutateAsync(skill.id)
      } else {
        await publish.mutateAsync(skill.id)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '操作失败')
    }
  }

  const isMutating = publish.isPending || unpublish.isPending

  return (
    <section
      className={`rounded-md border p-3 ${
        isPublic
          ? 'border-success bg-success-bg'
          : 'border-border-subtle bg-bg-canvas'
      }`}
      data-testid="publish-toggle"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-ui text-sm font-medium text-text-primary">
            {isPublic ? '🌐 已发布到市场' : '📦 仅本项目可见'}
          </p>
          <p className="mt-0.5 text-xs text-text-secondary">
            {isPublic
              ? '其他项目可在 Marketplace 看到并 import 这个 Skill (不影响已 import 的副本).'
              : '仅 owner 可发布到 Marketplace 让其他项目使用.'}
          </p>
          {isPublic && skill.published_at && (
            <p className="mt-0.5 font-mono text-[10px] text-text-tertiary">
              published_at: {new Date(skill.published_at).toLocaleString('zh-CN')}
            </p>
          )}
        </div>
        <Button
          variant={isPublic ? 'outline' : 'default'}
          size="sm"
          onClick={handleToggle}
          disabled={isMutating}
          data-testid="publish-toggle-btn"
        >
          {isMutating
            ? '处理中...'
            : isPublic
              ? '撤回'
              : '发布到市场'}
        </Button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-danger" data-testid="publish-error">
          {error}
        </p>
      )}
    </section>
  )
}
