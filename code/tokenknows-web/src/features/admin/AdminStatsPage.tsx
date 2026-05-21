/**
 * T15 · AdminStatsPage (实例管理控制台)
 *
 * 顶部 4 个数字卡 + 出域日志预览.
 * MVP: 数据走 MSW 的 admin handlers (尚未实现 → fallback 占位).
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Users, FolderOpen, FileText, Cpu, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface InstanceStats {
  users_total: number
  projects_total: number
  assets_this_month: number
  llm_tokens_this_month: number
  storage_used_bytes: number
  storage_limit_bytes: number
}

const FALLBACK_STATS: InstanceStats = {
  users_total: 12,
  projects_total: 3,
  assets_this_month: 27,
  llm_tokens_this_month: 248_910,
  storage_used_bytes: 1_840_582_133, // 1.7 GB
  storage_limit_bytes: 21_474_836_480, // 20 GB
}

export default function AdminStatsPage() {
  const navigate = useNavigate()
  const statsQuery = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: async (): Promise<InstanceStats> => {
      try {
        const { data } = await api.get<InstanceStats>('/admin/stats')
        return data
      } catch {
        return FALLBACK_STATS
      }
    },
    staleTime: 30_000,
  })

  const stats = statsQuery.data ?? FALLBACK_STATS

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <header className="bg-inverse-bg px-6 py-5 text-inverse-text">
        <h1 className="font-content text-h1 text-inverse-text">实例管理</h1>
        <p className="mt-1 font-ui text-caption text-inverse-muted">
          TokenKnows 私有化部署 · 仅 instance_admin 可见
        </p>
      </header>

      <main className="overflow-auto bg-bg-page px-6 py-6">
        <div className="mx-auto max-w-5xl space-y-6">
          {/* 4 个数字卡 */}
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              icon={<Users className="size-5 text-accent-primary-dark" />}
              label="实例用户"
              value={stats.users_total.toString()}
              trend="+2 本月"
            />
            <StatCard
              icon={<FolderOpen className="size-5 text-info" />}
              label="活跃项目"
              value={stats.projects_total.toString()}
              trend="0 本月"
            />
            <StatCard
              icon={<FileText className="size-5 text-success-dark" />}
              label="本月产出文档"
              value={stats.assets_this_month.toString()}
              trend="周报 18 / 技术方案 6 / ADR 3"
            />
            <StatCard
              icon={<Cpu className="size-5 text-warning" />}
              label="本月 LLM tokens"
              value={formatLargeNumber(stats.llm_tokens_this_month)}
              trend={`成本估算 $${(stats.llm_tokens_this_month * 0.000003).toFixed(2)}`}
            />
          </section>

          {/* 容量 */}
          <section className="rounded-md border border-border-subtle bg-bg-card p-4">
            <h2 className="font-content text-h3 text-text-primary">存储</h2>
            <p className="mt-1 font-ui text-caption text-text-muted">
              本实例 events / assets / S3 总用量
            </p>
            <div className="mt-3 space-y-1">
              <div className="flex items-center justify-between font-ui text-caption">
                <span className="text-text-secondary">
                  {formatBytes(stats.storage_used_bytes)} / {formatBytes(stats.storage_limit_bytes)}
                </span>
                <span className="text-text-muted">
                  {((stats.storage_used_bytes / stats.storage_limit_bytes) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bg-warm">
                <div
                  className="h-full rounded-full bg-accent-primary transition-all"
                  style={{
                    width: `${(stats.storage_used_bytes / stats.storage_limit_bytes) * 100}%`,
                  }}
                />
              </div>
            </div>
          </section>

          {/* 子页面 nav */}
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <NavCard
              title="用户列表"
              description="实例所有用户 · 邮箱 · 角色 · 最后登录"
              onClick={() => navigate('/admin/users')}
            />
            <NavCard
              title="审计日志"
              description="所有出域调用 / 发布 / 删除等敏感操作"
              onClick={() => navigate('/admin/audit')}
              disabled
              tooltip="T15 v2"
            />
            <NavCard
              title="LLM 全局配置"
              description="模型 allowlist + 出域审计级别"
              onClick={() => navigate('/admin/llm')}
              disabled
              tooltip="T14 v2"
            />
          </section>

          {/* MVP 提示 */}
          <section className="rounded-md border border-dashed border-border-medium bg-bg-card p-4 text-center">
            <p className="font-ui text-caption text-text-muted">
              MVP demo · 实际数据走 MSW fallback. 真后端接入 GET /admin/stats
              + GET /admin/users / GET /audit-log 端点后自动切换.
            </p>
          </section>
        </div>
      </main>
    </div>
  )
}

interface StatCardProps {
  icon: React.ReactNode
  label: string
  value: string
  trend?: string
}

function StatCard({ icon, label, value, trend }: StatCardProps) {
  return (
    <article className="rounded-md border border-border-subtle bg-bg-card p-4">
      <header className="flex items-center gap-2">
        {icon}
        <p className="font-ui text-caption text-text-muted">{label}</p>
      </header>
      <p className="mt-2 font-content text-h1 text-text-primary">{value}</p>
      {trend ? (
        <p className="mt-1 font-ui text-micro text-text-subtle">{trend}</p>
      ) : null}
    </article>
  )
}

interface NavCardProps {
  title: string
  description: string
  onClick: () => void
  disabled?: boolean
  tooltip?: string
}

function NavCard({ title, description, onClick, disabled, tooltip }: NavCardProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={cn(
        'flex h-auto items-start justify-between rounded-md border border-border-subtle bg-bg-card p-4 text-left transition',
        !disabled && 'hover:border-border-medium hover:bg-bg-warm',
      )}
      title={tooltip}
    >
      <div>
        <p className="font-content text-h3 text-text-primary">{title}</p>
        <p className="mt-0.5 font-ui text-caption text-text-muted">{description}</p>
      </div>
      <ChevronRight className="size-4 mt-0.5 shrink-0 text-text-subtle" />
    </Button>
  )
}

function formatLargeNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

function formatBytes(b: number): string {
  if (b >= 1_073_741_824) return `${(b / 1_073_741_824).toFixed(2)} GB`
  if (b >= 1_048_576) return `${(b / 1_048_576).toFixed(0)} MB`
  if (b >= 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${b} B`
}
