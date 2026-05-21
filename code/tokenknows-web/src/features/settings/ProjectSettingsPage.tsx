/**
 * T13 · ProjectSettingsPage
 *
 * Tab 切换 (使用 URL query ?tab=info|members|datasources|llm):
 *   - info: 基本信息 (name / description) - 可编辑
 *   - members: 成员表 (只读)
 *   - datasources: 数据源 (只读)
 *   - llm: T14 LLM 出域 sub-page
 *
 * MVP 简化: 不实现 删除项目 / 邀请成员 / 新增数据源 (留 v2)
 */

import { useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { Info, Users, Database, Shield, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import { useProject } from '../workbench/hooks/useProject'
import { LlmEgressPanel } from './tabs/LlmEgressPanel'
import { cn } from '@/lib/utils'

type Tab = 'info' | 'members' | 'datasources' | 'llm'

const TABS: { value: Tab; label: string; icon: typeof Info }[] = [
  { value: 'info', label: '基本信息', icon: Info },
  { value: 'members', label: '成员', icon: Users },
  { value: 'datasources', label: '数据源', icon: Database },
  { value: 'llm', label: 'LLM 与出域', icon: Shield },
]

export default function ProjectSettingsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const [search, setSearch] = useSearchParams()
  const tab = (search.get('tab') as Tab) || 'info'
  const projectQuery = useProject(projectId)

  if (projectQuery.error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="项目加载失败"
        error={projectQuery.error}
        onRetry={() => projectQuery.refetch()}
      />
    )
  }

  if (projectQuery.isLoading || !projectQuery.data) {
    return <LoadingSkeleton variant="document" />
  }

  const project = projectQuery.data

  return (
    <div className="grid h-full min-h-0 grid-cols-[220px_minmax(0,1fr)]">
      {/* 左侧 nav */}
      <nav
        className="flex flex-col gap-1 border-r border-border-subtle bg-bg-card p-3"
        aria-label="设置导航"
      >
        <h2 className="px-2 pt-2 pb-3 font-content text-h3 text-text-primary">
          项目设置
        </h2>
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.value
          return (
            <button
              key={t.value}
              type="button"
              onClick={() => setSearch({ tab: t.value })}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-2 font-ui text-body-sm transition',
                active
                  ? 'bg-accent-primary-light text-accent-primary-dark'
                  : 'text-text-secondary hover:bg-bg-warm',
              )}
            >
              <Icon className="size-3.5" />
              {t.label}
            </button>
          )
        })}
        <Link
          to={`/projects/${projectId}`}
          className="mt-auto rounded-md px-3 py-2 font-ui text-caption text-text-muted hover:bg-bg-warm"
        >
          ← 返回工作台
        </Link>
      </nav>

      {/* 右侧内容 */}
      <main className="overflow-auto bg-bg-page px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {tab === 'info' ? <InfoTab projectId={projectId} initialName={project.name} initialDescription={project.description} /> : null}
          {tab === 'members' ? <MembersTab /> : null}
          {tab === 'datasources' ? <DataSourcesTab /> : null}
          {tab === 'llm' ? <LlmEgressPanel projectId={projectId} /> : null}
        </div>
      </main>
    </div>
  )
}

// ─── Tabs ────────────────────────────────────────────────────────

interface InfoTabProps {
  projectId: string | undefined
  initialName: string
  initialDescription: string | null
}

function InfoTab({ projectId, initialName, initialDescription }: InfoTabProps) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // MVP: PATCH 端点未在后端实现, 这里仅做表单 UI 演示
  // (MSW projects handler 已支持 PATCH, 真后端在 T13 后端阶段补)
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!projectId) return
    setSaving(true)
    setError(null)
    try {
      // MVP: 走 MSW PATCH /projects/:id
      const { api } = await import('@/lib/api')
      await api.patch(`/projects/${projectId}`, { name, description })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      const { getErrorMessage } = await import('@/lib/api')
      setError(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="font-content text-h2 text-text-primary">基本信息</h2>
        <p className="font-ui text-caption text-text-muted">
          项目名称和简介, 修改后立即生效.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-md border border-border-subtle bg-bg-card p-4">
        <div>
          <label htmlFor="proj-name" className="font-ui text-caption font-medium text-text-secondary">
            项目名称
          </label>
          <input
            id="proj-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={saving}
            className="mt-1.5 w-full rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary focus:border-accent-primary focus:outline-none disabled:opacity-50"
            required
            maxLength={120}
          />
        </div>
        <div>
          <label htmlFor="proj-desc" className="font-ui text-caption font-medium text-text-secondary">
            简介
          </label>
          <textarea
            id="proj-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={saving}
            rows={3}
            className="mt-1.5 w-full resize-none rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary focus:border-accent-primary focus:outline-none disabled:opacity-50"
            maxLength={500}
          />
        </div>
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-danger">
            <AlertCircle className="size-4 mt-0.5 shrink-0" />
            <p className="font-ui text-caption">{error}</p>
          </div>
        ) : null}
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={saving || !name.trim()} className="font-ui">
            {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
            保存
          </Button>
          {saved ? (
            <span className="font-ui text-caption text-success-dark">已保存</span>
          ) : null}
        </div>
      </form>

      {/* Danger Zone - 仅占位 */}
      <section className="rounded-md border border-danger-border bg-danger-bg/30 p-4">
        <h3 className="font-content text-h3 text-danger">危险区</h3>
        <p className="mt-1 font-ui text-caption text-text-muted">
          删除项目会清除所有文档 / 事件 / 凭证. 此操作不可逆 (MVP 暂不支持, 留 v2).
        </p>
        <Button type="button" variant="outline" disabled className="mt-2 font-ui text-danger">
          删除项目 (v2)
        </Button>
      </section>
    </section>
  )
}

function MembersTab() {
  return (
    <section className="space-y-3">
      <header>
        <h2 className="font-content text-h2 text-text-primary">成员</h2>
        <p className="font-ui text-caption text-text-muted">
          项目成员列表 (只读). MVP 不支持邀请 / 编辑角色, 留 v2 接入 RBAC.
        </p>
      </header>
      <div className="rounded-md border border-border-subtle bg-bg-card">
        <table className="w-full font-ui text-body-sm">
          <thead className="border-b border-border-subtle bg-bg-warm">
            <tr className="text-left text-caption text-text-muted">
              <th className="px-3 py-2">成员</th>
              <th className="px-3 py-2">角色</th>
              <th className="px-3 py-2">加入时间</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border-subtle">
              <td className="px-3 py-2 text-text-primary">示例用户</td>
              <td className="px-3 py-2"><RoleBadge role="owner" /></td>
              <td className="px-3 py-2 font-mono text-caption text-text-subtle">2026/05/01</td>
            </tr>
            <tr>
              <td className="px-3 py-2 text-text-primary">Alice</td>
              <td className="px-3 py-2"><RoleBadge role="editor" /></td>
              <td className="px-3 py-2 font-mono text-caption text-text-subtle">2026/05/15</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}

function RoleBadge({ role }: { role: string }) {
  const map: Record<string, string> = {
    owner: 'bg-accent-primary-light text-accent-primary-dark',
    editor: 'bg-info-bg text-info',
    reviewer: 'bg-success-bg text-success-dark',
    viewer: 'bg-bg-warm text-text-muted',
  }
  return (
    <span className={cn('rounded-full px-2 py-0.5 font-ui text-micro', map[role] ?? 'bg-bg-warm text-text-muted')}>
      {role}
    </span>
  )
}

function DataSourcesTab() {
  return (
    <section className="space-y-3">
      <header>
        <h2 className="font-content text-h2 text-text-primary">数据源</h2>
        <p className="font-ui text-caption text-text-muted">
          通过插件 / GitHub App / 本地文档接入的数据源 (只读).
        </p>
      </header>
      <ul className="space-y-2">
        {[
          { type: 'github', name: 'TokenKnows/api', health: 'healthy' as const },
          { type: 'claude_code', name: 'install-john-mac', health: 'healthy' as const },
          { type: 'claude_code', name: 'install-bob-linux', health: 'degraded' as const },
        ].map((ds, i) => (
          <li key={i} className="flex items-center justify-between rounded-md border border-border-subtle bg-bg-card px-3 py-2">
            <div className="flex items-center gap-2">
              <Database className="size-4 text-text-secondary" />
              <span className="font-mono text-body-sm text-text-primary">{ds.name}</span>
              <span className="font-ui text-micro text-text-subtle uppercase tracking-wider">
                {ds.type}
              </span>
            </div>
            <HealthBadge health={ds.health} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function HealthBadge({ health }: { health: 'healthy' | 'degraded' | 'down' }) {
  const map = {
    healthy: { label: '正常', cls: 'bg-success-bg text-success-dark' },
    degraded: { label: '降级', cls: 'bg-warning-bg text-warning' },
    down: { label: '离线', cls: 'bg-danger-bg text-danger' },
  } as const
  const { label, cls } = map[health]
  return (
    <span className={cn('rounded-full px-2 py-0.5 font-ui text-micro', cls)}>
      {label}
    </span>
  )
}
