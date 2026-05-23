/**
 * MarketplacePage · v1.0.0 T70 · Skill 跨项目市场.
 *
 * 路由: /skills/marketplace (项目无关; 也可在项目内 /projects/:id/skills/marketplace)
 *
 * 行为:
 *   - 顶部搜索框 + min_trust 滑块
 *   - card grid: name / version / trust / project_id / preview / [import]
 *   - import 需要选目标项目 (用 useProjectStore.currentProjectId)
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import { EmptyState } from '@/components/shared/EmptyState'
import { useProjectStore } from '@/stores/projectStore'
import {
  useImportSkill,
  useMarketplaceSkills,
} from './hooks/useMarketplace'
import type { MarketplaceSkillCard } from '@/types/api'

export default function MarketplacePage() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId)
  const [searchInput, setSearchInput] = useState('')
  const [submittedQ, setSubmittedQ] = useState('')
  const [minTrust, setMinTrust] = useState(0)

  const q = useMarketplaceSkills(submittedQ, minTrust)

  function handleSearch(e: React.FormEvent): void {
    e.preventDefault()
    setSubmittedQ(searchInput.trim())
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="font-content text-2xl font-semibold text-text-primary">
          🌐 Skill Marketplace
        </h1>
        <p className="font-ui text-sm text-text-secondary">
          跨项目共享 reviewer-approved 的 Skill. 点击 import 复制到当前项目
          ({currentProjectId ?? '未选'}).
        </p>
      </header>

      {/* 搜索 + 过滤 */}
      <form
        onSubmit={handleSearch}
        className="flex flex-col gap-2 sm:flex-row sm:items-center"
        data-testid="marketplace-search"
      >
        <Input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="按名称 / 内容关键字搜索"
          data-testid="marketplace-q"
          className="flex-1"
        />
        <label className="flex items-center gap-2 font-ui text-sm text-text-secondary">
          <span>最低 trust</span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={minTrust * 100}
            onChange={(e) => setMinTrust(Number(e.target.value) / 100)}
            data-testid="marketplace-min-trust"
          />
          <span className="w-10 font-mono text-xs">
            {Math.round(minTrust * 100)}%
          </span>
        </label>
        <Button type="submit" size="sm" data-testid="marketplace-search-btn">
          搜索
        </Button>
      </form>

      {/* 结果 */}
      {q.isLoading && <LoadingSkeleton variant="list" />}
      {q.isError && (
        <ErrorState title="加载市场失败" onRetry={() => q.refetch()} />
      )}
      {q.data && q.data.items.length === 0 && (
        <EmptyState
          title="暂无匹配的 Skill"
          description="试试改关键词或降低 trust 阈值."
        />
      )}
      {q.data && q.data.items.length > 0 && (
        <ul
          className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3"
          data-testid="marketplace-list"
        >
          {q.data.items.map((s) => (
            <li key={s.skill_id}>
              <SkillMarketCard
                skill={s}
                currentProjectId={currentProjectId}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SkillMarketCard({
  skill,
  currentProjectId,
}: {
  skill: MarketplaceSkillCard
  currentProjectId: string | null
}) {
  const importSkill = useImportSkill(currentProjectId ?? '')
  const [imported, setImported] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canImport = !!currentProjectId

  async function handleImport(): Promise<void> {
    setError(null)
    try {
      await importSkill.mutateAsync({ source_skill_id: skill.skill_id })
      setImported(true)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Import 失败')
    }
  }

  return (
    <Card
      className="flex flex-col gap-2 p-4"
      data-testid={`market-card-${skill.skill_id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-1 font-content text-base font-semibold text-text-primary">
          {skill.name}
        </h3>
        <span className="rounded bg-accent-primary-light px-1.5 py-0.5 font-mono text-micro text-accent-primary-dark">
          v{skill.version}
        </span>
      </div>
      <div className="flex items-baseline gap-3 font-mono text-xs text-text-tertiary">
        <span>trust {Math.round(skill.trust_score * 100)}%</span>
        <span>{skill.acceptance_count}/{skill.usage_count}</span>
        <Link
          to={`/projects/${skill.project_id}`}
          className="truncate hover:underline"
          title={`原项目 ${skill.project_id}`}
        >
          📦 {skill.project_id}
        </Link>
      </div>
      <pre className="line-clamp-4 overflow-hidden rounded bg-bg-canvas p-2 font-mono text-xs text-text-secondary">
        {skill.skill_md_preview}
      </pre>
      {imported ? (
        <p className="text-xs text-success-dark" data-testid={`imported-${skill.skill_id}`}>
          ✓ 已导入到 {currentProjectId}
        </p>
      ) : (
        <Button
          size="sm"
          onClick={handleImport}
          disabled={!canImport || importSkill.isPending}
          data-testid={`import-${skill.skill_id}`}
        >
          {!canImport
            ? '请先选项目'
            : importSkill.isPending
              ? '导入中...'
              : `导入到 ${currentProjectId}`}
        </Button>
      )}
      {error && (
        <p className="text-xs text-danger" data-testid={`import-error-${skill.skill_id}`}>
          {error}
        </p>
      )}
    </Card>
  )
}
