/**
 * ReviewTimeline · v0.8.0 T63 · Skill 审批历史 timeline.
 *
 * 显示 review_history 按时间顺序; 空数组时不渲染.
 */

import type { ReviewRecord } from '@/types/api'

interface ReviewTimelineProps {
  history: ReviewRecord[]
}

const ACTION_LABEL: Record<ReviewRecord['action'], string> = {
  submit: '提交审批',
  approve: '✅ 批准',
  reject: '❌ 退回',
}

const ACTION_COLOR: Record<ReviewRecord['action'], string> = {
  submit: 'text-text-secondary',
  approve: 'text-success-dark',
  reject: 'text-danger',
}

export function ReviewTimeline({ history }: ReviewTimelineProps) {
  if (history.length === 0) return null

  return (
    <section
      data-testid="review-timeline"
      aria-label="Skill 审批历史"
      className="rounded-md border border-border-subtle bg-bg-canvas p-4"
    >
      <h3 className="mb-3 font-ui text-sm font-medium text-text-secondary">
        📜 审批历史 ({history.length})
      </h3>
      <ol className="flex flex-col gap-2">
        {history.map((r, i) => (
          <li
            key={`${r.reviewer_id}-${r.timestamp}-${i}`}
            data-testid={`review-record-${i}`}
            className="flex items-start gap-3 border-l-2 border-border-subtle pl-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span
                  className={`font-ui text-sm font-medium ${
                    ACTION_COLOR[r.action]
                  }`}
                >
                  {ACTION_LABEL[r.action]}
                </span>
                <span className="font-mono text-xs text-text-tertiary">
                  by {r.reviewer_id}
                </span>
                <span className="font-mono text-xs text-text-tertiary">
                  {new Date(r.timestamp).toLocaleString('zh-CN')}
                </span>
              </div>
              {r.note && (
                <p className="mt-1 text-xs text-text-secondary">{r.note}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
