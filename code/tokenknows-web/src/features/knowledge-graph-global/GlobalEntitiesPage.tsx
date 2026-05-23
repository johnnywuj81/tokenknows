/**
 * GlobalEntitiesPage · v1.6 T103 · 跨 project 实体浏览页 (类似 Skill marketplace).
 *
 * 路由: /global-entities
 *
 * 行为:
 *   - 顶部 search input + type filter (person/event/concept/artifact)
 *   - min_projects 过滤 (默认 2: 只看跨项目)
 *   - 列表展示: label / type / project_count / aliases / created_by
 *   - 展开行: 显示 linked project entities (project_id + asset_count)
 *   - 点击 linked → 不直接跳转 (跨 project, 用户可能没权限); 显示 project_id 只读
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import { EmptyState } from '@/components/shared/EmptyState'
import { Globe2, ChevronDown, ChevronUp, Users } from 'lucide-react'
import { api } from '@/lib/api'
import type { GlobalEntity } from '@/features/documents/knowledge-graph/hooks/useNodeEntity'
import type { NodeEntity } from '@/features/documents/knowledge-graph/hooks/useNodeEntity'

type EntityType = 'person' | 'event' | 'concept' | 'artifact'

const TYPE_LABEL: Record<EntityType, string> = {
  person: '人',
  event: '事件',
  concept: '概念',
  artifact: '产物',
}

const TYPE_COLOR: Record<EntityType, string> = {
  person: 'bg-warning-bg text-warning-dark',
  event: 'bg-info-bg text-info-dark',
  concept: 'bg-success-bg text-success-dark',
  artifact: 'bg-danger-bg text-danger-dark',
}

function useGlobalEntities(type: EntityType | null, q: string, minProjects: number) {
  return useQuery({
    queryKey: ['kg', 'global-entities', type, q, minProjects],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (type) params.set('type', type)
      if (q) params.set('q', q)
      params.set('min_projects', String(minProjects))
      const { data } = await api.get<GlobalEntity[]>(
        `/global/entities?${params.toString()}`,
      )
      return data
    },
    staleTime: 30_000,
  })
}

function useLinkedProjectEntities(globalId: string | null) {
  return useQuery({
    queryKey: ['kg', 'global-linked', globalId],
    queryFn: async () => {
      const { data } = await api.get<NodeEntity[]>(
        `/global/entities/${globalId}/projects`,
      )
      return data
    },
    enabled: Boolean(globalId),
    staleTime: 30_000,
  })
}

export default function GlobalEntitiesPage() {
  const [searchInput, setSearchInput] = useState('')
  const [submittedQ, setSubmittedQ] = useState('')
  const [typeFilter, setTypeFilter] = useState<EntityType | null>(null)
  const [minProjects, setMinProjects] = useState(2)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const query = useGlobalEntities(typeFilter, submittedQ, minProjects)

  function handleSearch(e: React.FormEvent): void {
    e.preventDefault()
    setSubmittedQ(searchInput.trim())
  }

  return (
    <div className="flex flex-col gap-4 p-6" data-testid="global-entities-page">
      <header>
        <h1 className="flex items-center gap-2 font-content text-2xl font-semibold text-text-primary">
          <Globe2 className="size-6" />
          全局实体浏览
        </h1>
        <p className="font-ui text-sm text-text-secondary">
          跨 project 共享的实体 (publish_to_global 后出现). 默认仅显示出现在 ≥{minProjects} 个 project 的.
        </p>
      </header>

      {/* 搜索 + 过滤 */}
      <form
        onSubmit={handleSearch}
        className="flex flex-col gap-2 sm:flex-row sm:items-center"
        data-testid="global-entities-search"
      >
        <Input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="搜索实体 label / aliases…"
          className="sm:max-w-sm"
        />
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={typeFilter === null ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTypeFilter(null)}
            data-testid="type-filter-all"
          >
            全部
          </Button>
          {(['person', 'event', 'concept', 'artifact'] as EntityType[]).map((t) => (
            <Button
              key={t}
              type="button"
              variant={typeFilter === t ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTypeFilter(t)}
              data-testid={`type-filter-${t}`}
            >
              {TYPE_LABEL[t]}
            </Button>
          ))}
        </div>
        <label className="flex items-center gap-1 font-ui text-sm text-text-secondary">
          跨 project ≥
          <input
            type="number"
            min={1}
            max={50}
            value={minProjects}
            onChange={(e) => setMinProjects(Math.max(1, Number(e.target.value) || 1))}
            className="w-12 rounded border border-border-subtle px-2 py-0.5 font-mono"
            data-testid="min-projects-input"
          />
        </label>
        <Button type="submit" size="sm">搜索</Button>
      </form>

      {/* 列表 */}
      {query.isLoading ? (
        <LoadingSkeleton variant="list" />
      ) : query.error ? (
        <ErrorState
          title="加载失败"
          description="后端 /global/entities 不可达"
          onRetry={() => query.refetch()}
        />
      ) : !query.data || query.data.length === 0 ? (
        <EmptyState
          title="暂无跨 project 全局实体"
          description={`提示: 在 KG 节点面板里点 "发布到全局" 把 project 实体提交进来. 当前过滤: type=${typeFilter ?? '全部'}, ≥${minProjects} project.`}
        />
      ) : (
        <ul
          data-testid="global-entities-list"
          className="flex flex-col gap-2"
        >
          {query.data.map((ent) => (
            <li key={ent.id}>
              <GlobalEntityRow
                entity={ent}
                expanded={expandedId === ent.id}
                onToggle={() => setExpandedId(expandedId === ent.id ? null : ent.id)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface GlobalEntityRowProps {
  entity: GlobalEntity
  expanded: boolean
  onToggle: () => void
}

function GlobalEntityRow({ entity, expanded, onToggle }: GlobalEntityRowProps) {
  const linkedQuery = useLinkedProjectEntities(expanded ? entity.id : null)
  const t = entity.type as EntityType

  return (
    <div
      data-testid={`global-entity-${entity.id}`}
      className="rounded-lg border border-border-subtle bg-bg-card p-3"
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-3 text-left"
        aria-expanded={expanded}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-1.5 py-0.5 font-ui text-micro font-medium ${TYPE_COLOR[t]}`}
            >
              {TYPE_LABEL[t]}
            </span>
            <h3 className="line-clamp-1 font-content text-h4 text-text-primary">
              {entity.label}
            </h3>
          </div>
          {entity.aliases.length > 0 ? (
            <p className="mt-1 font-ui text-caption text-text-muted">
              也叫: {entity.aliases.join(', ')}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-caption text-text-secondary">
          <Users className="size-3 text-text-subtle" />
          <span data-testid={`project-count-${entity.id}`}>
            {entity.project_count} project
          </span>
          {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </div>
      </button>
      {expanded ? (
        <div
          data-testid={`global-entity-expanded-${entity.id}`}
          className="mt-3 border-t border-border-subtle pt-3"
        >
          {linkedQuery.isLoading ? (
            <p className="font-ui text-caption text-text-muted">加载关联中…</p>
          ) : !linkedQuery.data || linkedQuery.data.length === 0 ? (
            <p className="font-ui text-caption text-text-muted">无关联</p>
          ) : (
            <ul className="space-y-1">
              {linkedQuery.data.map((pe) => (
                <li
                  key={pe.id}
                  className="flex items-center justify-between rounded bg-bg-warm/40 px-2 py-1.5 font-ui text-caption"
                >
                  <span className="font-mono text-text-secondary">
                    {pe.project_id}
                  </span>
                  <span className="font-mono text-text-subtle">
                    {pe.source_refs.length} 个引用
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}
