/**
 * GovernancePage · v0.8.0 T64 · Skill 池治理 dashboard.
 *
 * 路由: /projects/:id/skills/governance
 *
 * 5 统计卡 + 3 candidate count 卡 + 2 手动 sweep 按钮.
 */

import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import {
  useRunDeprecationSweep,
  useRunTrustRecompute,
  useSkillGovernanceSummary,
} from './hooks/useSkills'

export default function GovernancePage() {
  const { id: projectId = '' } = useParams<{ id: string }>()
  const q = useSkillGovernanceSummary(projectId)
  const runTrust = useRunTrustRecompute(projectId)
  const runDep = useRunDeprecationSweep(projectId)

  if (q.isLoading) return <LoadingSkeleton variant="list" />
  if (q.isError) {
    return <ErrorState title="加载 Skill 治理失败" onRetry={() => q.refetch()} />
  }
  const data = q.data
  if (!data) return null

  const totalActive = data.by_status.active ?? 0
  const totalDraft = data.by_status.draft ?? 0
  const totalDeprecated = data.by_status.deprecated ?? 0
  const pendingReview = data.by_review_state.pending_review ?? 0

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1 className="font-content text-2xl font-semibold text-text-primary">
          Skill 治理看板
        </h1>
        <p className="font-ui text-sm text-text-secondary">
          每日自动跑 trust 重算 (02:00) / evolve (03:00) / deprecation (03:10);
          也可在下方手动触发.
        </p>
      </header>

      {/* 总览卡 */}
      <section
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="governance-stats"
      >
        <StatCard label="总数" value={data.total} />
        <StatCard label="✅ Active" value={totalActive} accent="success" />
        <StatCard label="📝 Draft" value={totalDraft} />
        <StatCard label="📦 Deprecated" value={totalDeprecated} accent="muted" />
        <StatCard label="⏳ 待审批" value={pendingReview} accent="warning" />
        <StatCard
          label="平均 trust"
          value={`${Math.round(data.avg_trust_score * 100)}%`}
        />
      </section>

      {/* 候选卡 (Pending sweep targets) */}
      <section>
        <h2 className="font-content text-lg font-semibold text-text-primary mb-3">
          待处理候选
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="governance-candidates">
          <CandidateCard
            label="🌱 待 Evolve"
            value={data.evolve_candidates}
            description="usage ≥ 20 且 acc_rate < 0.5 的 skill"
            actionLabel="（自动每天 03:00 跑）"
          />
          <CandidateCard
            label="💤 Dormant"
            value={data.dormant_candidates}
            description="60 天未使用的 active skill"
          />
          <CandidateCard
            label="📉 Low-trust"
            value={data.low_trust_candidates}
            description="trust_score < 0.2 的 active skill"
          />
        </div>
      </section>

      {/* 手动触发 */}
      <section>
        <h2 className="font-content text-lg font-semibold text-text-primary mb-3">
          手动触发
        </h2>
        <Card className="flex flex-col gap-3 p-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-ui text-sm font-medium text-text-primary">
                重算 trust_score
              </p>
              <p className="text-xs text-text-secondary">
                立刻刷新所有 active/draft skill 的 trust_score (recency_decay).
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => runTrust.mutate()}
              disabled={runTrust.isPending}
              data-testid="trust-recompute-btn"
            >
              {runTrust.isPending ? '运行中...' : '立即跑'}
            </Button>
          </div>
          {runTrust.data && (
            <p className="text-xs text-text-tertiary" data-testid="trust-result">
              ✓ scanned={runTrust.data.scanned}, updated={runTrust.data.updated},
              skipped={runTrust.data.skipped}
            </p>
          )}

          <hr className="border-border-subtle" />

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-ui text-sm font-medium text-text-primary">
                运行 deprecation sweep
              </p>
              <p className="text-xs text-text-secondary">
                把 dormant + low_trust 候选 skill 转 deprecated 状态 + 通知 contributors.
              </p>
            </div>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => runDep.mutate()}
              disabled={runDep.isPending}
              data-testid="deprecation-sweep-btn"
            >
              {runDep.isPending ? '运行中...' : '立即跑'}
            </Button>
          </div>
          {runDep.data && (
            <p
              className="text-xs text-text-tertiary"
              data-testid="deprecation-result"
            >
              ✓ 完成. 剩余候选: {runDep.data.remaining_candidates}
            </p>
          )}
        </Card>
      </section>
    </div>
  )
}

interface StatCardProps {
  label: string
  value: number | string
  accent?: 'success' | 'warning' | 'muted'
}

function StatCard({ label, value, accent }: StatCardProps) {
  const colorMap: Record<NonNullable<StatCardProps['accent']>, string> = {
    success: 'text-success-dark',
    warning: 'text-warning-dark',
    muted: 'text-text-tertiary',
  }
  const valueClass = accent ? colorMap[accent] : 'text-text-primary'
  return (
    <Card className="p-4">
      <p className="font-ui text-xs text-text-secondary">{label}</p>
      <p className={`mt-1 font-content text-2xl font-semibold ${valueClass}`}>
        {value}
      </p>
    </Card>
  )
}

interface CandidateCardProps {
  label: string
  value: number
  description: string
  actionLabel?: string
}

function CandidateCard({
  label,
  value,
  description,
  actionLabel,
}: CandidateCardProps) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <div className="flex items-baseline justify-between">
        <p className="font-ui text-sm font-medium text-text-primary">{label}</p>
        <p className="font-content text-xl font-semibold text-warning-dark">
          {value}
        </p>
      </div>
      <p className="text-xs text-text-secondary">{description}</p>
      {actionLabel && (
        <p className="font-mono text-[10px] text-text-tertiary">
          {actionLabel}
        </p>
      )}
    </Card>
  )
}
