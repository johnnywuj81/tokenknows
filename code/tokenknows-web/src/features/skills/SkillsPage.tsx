/**
 * SkillsPage · /projects/:id/skills (v0.2)
 *
 * MVP 实现:
 *   - 左栏: 按 trust_score DESC 排序的 skill 列表
 *   - 右栏: 选中 skill 的详情 (SKILL.md 渲染 + 元数据卡片)
 *   - 顶栏 3 tab: 当前 active / 草稿 draft / 归档 deprecated
 *   - 操作: lock / unlock / delete / evolve
 *
 * 不在 MVP 内:
 *   - TipTap SKILL.md 在线编辑 (留 v0.3)
 *   - 跨项目导入 / 导出
 */

import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Skill, SkillStatus } from '@/types/api'
import { ConsentPending } from './components/ConsentPending'
import { ReviewActions } from './components/ReviewActions'
import {
  useDeleteSkill,
  useEvolveSkill,
  useLockSkill,
  useSkills,
  useUnlockSkill,
} from './hooks/useSkills'

export default function SkillsPage() {
  const { id: projectId = '' } = useParams<{ id: string }>()
  const [tab, setTab] = useState<SkillStatus>('active')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const skillsQ = useSkills(projectId, tab)
  const lock = useLockSkill(projectId)
  const unlock = useUnlockSkill(projectId)
  const evolve = useEvolveSkill(projectId)
  const del = useDeleteSkill(projectId)

  const selected = useMemo(
    () => skillsQ.data?.find((s) => s.id === selectedId) ?? null,
    [skillsQ.data, selectedId],
  )

  if (skillsQ.isLoading) return <LoadingSkeleton variant="list" />
  if (skillsQ.isError) {
    return (
      <ErrorState
        title="加载技能失败"
        description="网络错误或后端未启动"
        onRetry={() => skillsQ.refetch()}
      />
    )
  }
  const skills = skillsQ.data ?? []

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-content text-2xl font-semibold text-text-primary">
            Agent 专家技能
          </h1>
          <p className="font-ui text-sm text-text-secondary">
            从已批准章节蒸馏的可复用 skill,自动注入下次生成提升质量
          </p>
        </div>
      </header>

      <Tabs value={tab} onValueChange={(v) => setTab(v as SkillStatus)}>
        <TabsList>
          <TabsTrigger value="active">当前 (active)</TabsTrigger>
          <TabsTrigger value="draft">草稿 (draft)</TabsTrigger>
          <TabsTrigger value="pending_contributor_consent">
            待 contributor 同意
          </TabsTrigger>
          <TabsTrigger value="deprecated">归档 (deprecated)</TabsTrigger>
        </TabsList>
      </Tabs>

      {skills.length === 0 ? (
        <EmptyState
          title={`暂无 ${tab} 状态的技能`}
          description="在文档审批后,从章节蒸馏出技能,会出现在此处"
        />
      ) : (
        <div className="grid grid-cols-[320px_1fr] gap-4">
          <SkillList
            skills={skills}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          {selected ? (
            <SkillDetail
              skill={selected}
              onLock={() => lock.mutate(selected.id)}
              onUnlock={() => unlock.mutate(selected.id)}
              onEvolve={() => evolve.mutate(selected.id)}
              onDelete={() => del.mutate(selected.id)}
              isMutating={
                lock.isPending ||
                unlock.isPending ||
                evolve.isPending ||
                del.isPending
              }
            />
          ) : (
            <EmptyState
              title="选中一个技能查看详情"
              description="点击左侧任一条目"
            />
          )}
        </div>
      )}
    </div>
  )
}

interface SkillListProps {
  skills: Skill[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function SkillList({ skills, selectedId, onSelect }: SkillListProps) {
  return (
    <div className="flex flex-col gap-2">
      {skills.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          type="button"
          className={`rounded-lg border p-3 text-left transition-colors ${
            selectedId === s.id
              ? 'border-brand bg-bg-card-hover'
              : 'border-border-subtle bg-bg-card hover:border-brand-subtle'
          }`}
        >
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-medium text-text-primary">
              {s.name}
            </span>
            <span className="text-xs text-text-tertiary">v{s.version}</span>
          </div>
          <p className="mt-1 text-xs text-text-secondary">
            trust {Math.round(s.metrics.trust_score * 100)}% · used{' '}
            {s.metrics.usage_count} · accepted {s.metrics.acceptance_count}
            {s.locked ? ' · 已锁定' : ''}
          </p>
        </button>
      ))}
    </div>
  )
}

interface SkillDetailProps {
  skill: Skill
  onLock: () => void
  onUnlock: () => void
  onEvolve: () => void
  onDelete: () => void
  isMutating: boolean
}

function SkillDetail({
  skill,
  onLock,
  onUnlock,
  onEvolve,
  onDelete,
  isMutating,
}: SkillDetailProps) {
  return (
    <Card className="flex flex-col gap-4 p-5">
      {/* v0.5.1 T51 · pending_contributor_consent 时显示 banner */}
      <ConsentPending skill={skill} />

      {/* v0.6.0 T58 · Reviewer 审批操作区 */}
      <ReviewActions skill={skill} />

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-content text-xl font-semibold text-text-primary">
            {skill.name}
          </h2>
          <p className="text-xs text-text-tertiary">
            v{skill.version} · {skill.status} · trust{' '}
            {Math.round(skill.metrics.trust_score * 100)}% · accepted{' '}
            {skill.metrics.acceptance_count}/{skill.metrics.usage_count}
          </p>
        </div>
        <div className="flex gap-2">
          {skill.locked ? (
            <Button
              variant="outline"
              size="sm"
              onClick={onUnlock}
              disabled={isMutating}
            >
              解锁
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={onLock}
              disabled={isMutating}
            >
              锁定
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={onEvolve}
            disabled={isMutating || skill.locked}
          >
            强制进化
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onDelete}
            disabled={isMutating}
          >
            删除
          </Button>
        </div>
      </div>

      <section>
        <h3 className="font-ui mb-2 text-sm font-medium text-text-secondary">
          SKILL.md
        </h3>
        <pre className="max-h-[60vh] overflow-auto rounded-md border border-border-subtle bg-bg-canvas p-3 font-mono text-xs text-text-primary">
          {skill.skill_md}
        </pre>
      </section>
    </Card>
  )
}
