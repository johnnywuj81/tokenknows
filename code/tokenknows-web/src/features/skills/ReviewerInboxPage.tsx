/**
 * ReviewerInboxPage · v0.6.0 T58 · 待审批 Skill 列表.
 *
 * 路由: /projects/:id/skills/review-inbox
 *
 * MVP: 任何 contributor 都可以是 reviewer; 实际生产应换 reviewer role 校验.
 * 列出 review_state=pending_review 的所有 skill, 点击进详情页操作.
 */

import { Link, useParams } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { usePendingReviewSkills } from './hooks/useSkills'

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const min = Math.floor(ms / 60000)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  return `${Math.floor(hr / 24)} 天前`
}

export default function ReviewerInboxPage() {
  const { id: projectId = '' } = useParams<{ id: string }>()
  const q = usePendingReviewSkills(projectId)

  if (q.isLoading) return <LoadingSkeleton variant="list" />
  if (q.isError) {
    return (
      <ErrorState
        title="加载待审 Skill 失败"
        onRetry={() => q.refetch()}
      />
    )
  }

  const items = q.data ?? []

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="font-content text-2xl font-semibold text-text-primary">
          Reviewer 收件箱
        </h1>
        <p className="font-ui text-sm text-text-secondary">
          等待审批的 Skill 草稿; 通过后自动进 active 状态可被下游生成注入.
        </p>
      </header>

      {items.length === 0 ? (
        <EmptyState
          title="没有待审批的 Skill"
          description="作者提交后会在这里出现 🌿"
        />
      ) : (
        <ul
          className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3"
          data-testid="reviewer-inbox-list"
        >
          {items.map((s) => {
            const latestSubmit = [...s.review_history]
              .reverse()
              .find((r) => r.action === 'submit')
            return (
              <li key={s.id}>
                <Link
                  to={`/projects/${projectId}/skills`}
                  state={{ selectedSkillId: s.id }}
                  data-testid={`reviewer-inbox-item-${s.id}`}
                >
                  <Card className="flex flex-col gap-2 p-4 transition hover:border-accent-primary">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="line-clamp-1 font-content text-base font-semibold text-text-primary">
                        {s.name}
                      </h3>
                      <span className="rounded bg-warning-bg px-1.5 py-0.5 font-ui text-micro font-medium text-warning-dark">
                        待审批
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary">
                      {s.contributors.length} 位贡献者 · v{s.version}
                    </p>
                    {latestSubmit && (
                      <p className="font-mono text-xs text-text-tertiary">
                        {latestSubmit.reviewer_id} 提交于{' '}
                        {timeAgo(latestSubmit.timestamp)}
                      </p>
                    )}
                  </Card>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
