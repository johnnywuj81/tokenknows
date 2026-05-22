/**
 * v0.4 T33 + T35 · 自动触发 Tab (在 T13 设置 Tab 内)
 *
 * - 列出所有规则 (实例级默认 + 项目自定义) + 模式徽标 + 启停 Switch
 * - 点行打开 Sheet 详情抽屉 (描述 / 触发条件 / 频率限制 / 最近触发历史)
 * - 当所有规则都 disabled 时显示 onboarding 卡 (T35 引导向导, 不弹 Dialog 更不打扰)
 *
 * 后端 T32 未上线; 完全走 MSW handlers/auto-triggers.ts.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Bot,
  Calendar,
  CheckCircle2,
  Cog,
  Gauge,
  GitPullRequest,
  History,
  ListChecks,
  Sparkles,
  Trash2,
  XCircle,
  Loader2,
  Plus,
  ShieldOff,
  Zap,
} from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorState } from '@/components/shared/ErrorState'
import { RuleEditorDialog } from './RuleEditorDialog'
import { cn } from '@/lib/utils'
import type {
  QuotaResponse,
  TriggerExecution,
  TriggerMode,
  TriggerRule,
} from '@/types/api'

interface AutoTriggersPanelProps {
  projectId: string | undefined
}

const MODE_META: Record<TriggerMode, { label: string; icon: typeof Calendar; tint: string }> = {
  cron: { label: '定时', icon: Calendar, tint: 'text-info' },
  event: { label: '事件', icon: GitPullRequest, tint: 'text-accent-primary-dark' },
  threshold: { label: '阈值', icon: Gauge, tint: 'text-warning' },
  mention: { label: '@机器人', icon: Bot, tint: 'text-text-muted' },
}

const ASSET_TYPE_LABEL: Record<string, string> = {
  weekly_report: '周报',
  tech_design: '技术方案',
  adr: 'ADR',
  incident: '问题复盘',
  book: '书籍',
  agent_skill: 'Agent Skill',
}

// ──────────────────────────────────────────────────────────


export function AutoTriggersPanel({ projectId }: AutoTriggersPanelProps) {
  const [openRuleId, setOpenRuleId] = useState<string | null>(null)
  const [onboardingSelected, setOnboardingSelected] = useState<Set<string>>(new Set())
  const [editorOpen, setEditorOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<TriggerRule | null>(null)

  const rulesQuery = useQuery({
    queryKey: ['auto-trigger', projectId, 'rules'],
    queryFn: async (): Promise<TriggerRule[]> => {
      const { data } = await api.get(`/projects/${projectId}/auto-triggers/rules`)
      return data.data ?? []
    },
    enabled: Boolean(projectId),
  })

  if (rulesQuery.error) {
    return (
      <ErrorState
        title="规则加载失败"
        error={rulesQuery.error}
        onRetry={() => rulesQuery.refetch()}
      />
    )
  }

  if (rulesQuery.isLoading || !rulesQuery.data) {
    return <LoadingSkeleton variant="list" />
  }

  const rules = rulesQuery.data
  const enabledCount = rules.filter((r) => r.enabled).length
  const showOnboarding = enabledCount === 0 && rules.length > 0
  const openRule = rules.find((r) => r.id === openRuleId) ?? null

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
            T13 · 项目设置 → 自动触发 (v0.4)
          </p>
          <h2 className="font-content text-h2 text-text-primary">自动触发规则</h2>
          <p className="text-body-sm text-text-muted">
            基于研发过程信号自动生成文档 / Skill。命中后有 <strong>5 分钟撤回窗口</strong>，
            用户可在窗口内取消。所有自动生成的 asset 仍走完整 Reviewer 审批流。
          </p>
        </div>
        <Button
          onClick={() => setEditorOpen(true)}
          className="font-ui shrink-0"
        >
          <Plus className="size-3.5" />
          新建规则
        </Button>
      </header>

      {/* v0.4.4 · 月配额仪表盘 (体验要素 #32) */}
      <QuotaCard projectId={projectId} />

      {/* 引导卡: 全部 disabled 时显示 (T35 体验要素 #35) */}
      {showOnboarding && (
        <OnboardingCard
          projectId={projectId}
          rules={rules}
          selected={onboardingSelected}
          onToggle={(id) => {
            const next = new Set(onboardingSelected)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            setOnboardingSelected(next)
          }}
        />
      )}

      {/* 状态条 */}
      <div className="flex items-center gap-3 rounded-md bg-bg-card border border-border-subtle px-4 py-3 font-ui text-body-sm">
        <ListChecks className="size-4 text-text-muted" />
        <span className="text-text-secondary">
          共 {rules.length} 条规则
          <span className="mx-2 text-text-subtle">·</span>
          <span className="text-success-dark">{enabledCount} 启用</span>
          <span className="mx-2 text-text-subtle">·</span>
          <span className="text-text-muted">{rules.length - enabledCount} 暂停</span>
        </span>
      </div>

      {/* 规则列表 */}
      <ul className="space-y-2" aria-label="规则列表">
        {rules.map((rule) => (
          <RuleListItem
            key={rule.id}
            rule={rule}
            projectId={projectId}
            onOpen={() => setOpenRuleId(rule.id)}
            onDeleteClick={() => setDeleteTarget(rule)}
          />
        ))}
      </ul>

      {/* 详情抽屉 */}
      <Sheet open={openRule !== null} onOpenChange={(open) => !open && setOpenRuleId(null)}>
        <SheetContent side="right" className="w-[480px] overflow-y-auto">
          {openRule && <RuleDetail rule={openRule} projectId={projectId} />}
        </SheetContent>
      </Sheet>

      {/* v0.4.3 · 新建规则 Dialog (builder) */}
      <RuleEditorDialog
        projectId={projectId}
        open={editorOpen}
        onOpenChange={setEditorOpen}
      />

      {/* v0.4.3 · 删除二次确认 */}
      <DeleteConfirmDialog
        rule={deleteTarget}
        projectId={projectId}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  )
}


// ─── 删除二次确认 ─────────────────────────────────────────


function DeleteConfirmDialog({
  rule, projectId, onClose,
}: {
  rule: TriggerRule | null
  projectId: string | undefined
  onClose: () => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => {
      if (!rule) return
      await api.delete(
        `/projects/${projectId}/auto-triggers/rules/${rule.id}`,
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['auto-trigger', projectId, 'rules'],
      })
      onClose()
    },
  })

  const isInstanceLevel = rule?.project_id === null

  return (
    <Dialog open={rule !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-content">
            <Trash2 className="inline size-4 mr-1 text-danger" />
            删除规则？
          </DialogTitle>
          <DialogDescription>
            将永久删除规则 <strong>{rule?.name}</strong>。
            该规则的历史执行记录也会被级联清理。
            {isInstanceLevel && (
              <p className="mt-2 text-danger">
                ⚠ 这是实例级默认规则，不能通过 UI 删除。请改用启停 Switch 关闭。
              </p>
            )}
          </DialogDescription>
        </DialogHeader>
        {del.isError && (
          <p className="text-caption text-danger">
            删除失败: {(del.error as Error).message}
          </p>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="destructive"
            disabled={isInstanceLevel || del.isPending}
            onClick={() => del.mutate()}
          >
            {del.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Trash2 className="size-3.5" />
            )}
            永久删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ──────────────────────────────────────────────────────────
// 单行规则
// ──────────────────────────────────────────────────────────


interface RuleListItemProps {
  rule: TriggerRule
  projectId: string | undefined
  onOpen: () => void
  onDeleteClick: () => void
}

function RuleListItem({ rule, projectId, onOpen, onDeleteClick }: RuleListItemProps) {
  const qc = useQueryClient()
  const ModeIcon = MODE_META[rule.mode].icon

  const toggleMutation = useMutation({
    mutationFn: async (next: boolean) => {
      const { data } = await api.patch(
        `/projects/${projectId}/auto-triggers/rules/${rule.id}`,
        { enabled: next },
      )
      return data as TriggerRule
    },
    // optimistic update + 失败回滚
    onMutate: async (next) => {
      await qc.cancelQueries({ queryKey: ['auto-trigger', projectId, 'rules'] })
      const prev = qc.getQueryData<TriggerRule[]>([
        'auto-trigger', projectId, 'rules',
      ])
      qc.setQueryData<TriggerRule[]>(
        ['auto-trigger', projectId, 'rules'],
        (old) => old?.map((r) => (r.id === rule.id ? { ...r, enabled: next } : r)),
      )
      return { prev }
    },
    onError: (_err, _next, ctx) => {
      if (ctx?.prev) qc.setQueryData(['auto-trigger', projectId, 'rules'], ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['auto-trigger', projectId, 'rules'] })
    },
  })

  return (
    <li className="rounded-md border border-border-subtle bg-bg-card transition hover:border-border-medium">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <ModeIcon className={cn('size-4 shrink-0', MODE_META[rule.mode].tint)} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="font-ui text-body font-medium text-text-primary">
              {rule.name}
            </span>
            <Badge variant="secondary" className="font-ui text-micro">
              {MODE_META[rule.mode].label}
            </Badge>
            <Badge variant="outline" className="font-ui text-micro">
              {ASSET_TYPE_LABEL[rule.asset_type] ?? rule.asset_type}
            </Badge>
            <Badge variant="outline" className="font-ui text-micro text-text-muted">
              优先级 {rule.priority}
            </Badge>
          </div>
          <p className="line-clamp-1 text-caption text-text-muted">{rule.description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Switch
            checked={rule.enabled}
            disabled={toggleMutation.isPending}
            onClick={(e) => e.stopPropagation()}
            onCheckedChange={(next) => toggleMutation.mutate(next)}
          />
          {rule.project_id !== null && (
            // 项目级规则可删; 实例级 (project_id=null) 隐藏按钮
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onDeleteClick(); }}
              className="rounded-md p-1.5 text-text-muted hover:bg-danger-bg hover:text-danger transition"
              aria-label="删除规则"
              title="删除规则"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      </button>
    </li>
  )
}

// ──────────────────────────────────────────────────────────
// 详情抽屉
// ──────────────────────────────────────────────────────────


interface RuleDetailProps {
  rule: TriggerRule
  projectId: string | undefined
}

function RuleDetail({ rule, projectId }: RuleDetailProps) {
  const qc = useQueryClient()
  const executionsQuery = useQuery({
    queryKey: ['auto-trigger', projectId, 'rules', rule.id, 'executions'],
    queryFn: async (): Promise<TriggerExecution[]> => {
      const { data } = await api.get(
        `/projects/${projectId}/auto-triggers/executions?rule_id=${rule.id}&limit=20`,
      )
      return data.data ?? []
    },
    enabled: Boolean(projectId),
  })

  // v0.4 体验要素 #30 演示: 立即触发短窗口 (30s 撤回)
  const testFireMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        `/projects/${projectId}/auto-triggers/rules/${rule.id}/test-fire`,
      )
      return data
    },
    onSuccess: () => {
      // 刷新当前规则的执行历史 + 全局 scheduled 列表 (浮动通知卡用)
      qc.invalidateQueries({
        queryKey: ['auto-trigger', projectId, 'rules', rule.id, 'executions'],
      })
      qc.invalidateQueries({
        queryKey: ['auto-trigger', projectId, 'executions'],
      })
    },
  })

  const ModeIcon = MODE_META[rule.mode].icon

  return (
    <>
      <SheetHeader>
        <SheetTitle className="flex items-center gap-2 font-content text-h3">
          <ModeIcon className={cn('size-5', MODE_META[rule.mode].tint)} />
          {rule.name}
        </SheetTitle>
        <SheetDescription className="text-body-sm">{rule.description}</SheetDescription>
      </SheetHeader>

      {/* 演示按钮: 立即触发 (30s 短窗口) */}
      {rule.enabled && (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-accent-primary bg-accent-primary-light/30 p-3">
          <Zap className="size-4 text-accent-primary-dark shrink-0" />
          <div className="flex-1 text-caption text-text-secondary">
            <strong>演示:</strong> 立即触发一次 (撤回窗口 30 秒) ·
            右下角浮动通知会显示倒计时
          </div>
          <Button
            size="sm"
            disabled={testFireMutation.isPending || testFireMutation.isSuccess}
            onClick={() => testFireMutation.mutate()}
            className="font-ui shrink-0"
          >
            {testFireMutation.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : testFireMutation.isSuccess ? (
              <CheckCircle2 className="size-3.5" />
            ) : (
              <Zap className="size-3.5" />
            )}
            {testFireMutation.isSuccess ? '已触发' : '立即触发演示'}
          </Button>
        </div>
      )}

      {/* 触发条件 */}
      <section className="mt-6 space-y-2">
        <h3 className="font-ui text-eyebrow uppercase text-text-muted">触发条件</h3>
        <ul className="space-y-1 rounded-md bg-bg-page p-3 font-mono text-caption text-text-secondary">
          {rule.cron_expr && (
            <li>
              cron: <strong>{rule.cron_expr}</strong>
              <span className="ml-2 text-text-muted">({describeCron(rule.cron_expr)})</span>
            </li>
          )}
          {rule.event_match && (
            <>
              <li>事件类型: {rule.event_match.event_type}</li>
              {rule.event_match.label_any && rule.event_match.label_any.length > 0 && (
                <li>labels 含: {rule.event_match.label_any.join(' / ')}</li>
              )}
            </>
          )}
          {rule.threshold_spec && (
            <li>
              {rule.threshold_spec.metric} {rule.threshold_spec.comparator}{' '}
              <strong>{rule.threshold_spec.value}</strong>
              {rule.threshold_spec.and_not_exists_asset_of_type && (
                <span className="ml-2 text-text-muted">
                  (且未生成过 {rule.threshold_spec.and_not_exists_asset_of_type})
                </span>
              )}
            </li>
          )}
          {rule.extra_condition && (
            <li>
              附加: {rule.extra_condition.metric} {rule.extra_condition.comparator}{' '}
              <strong>{rule.extra_condition.value}</strong>
            </li>
          )}
        </ul>
      </section>

      {/* 频率限制 */}
      <section className="mt-6 space-y-2">
        <h3 className="font-ui text-eyebrow uppercase text-text-muted">频率限制</h3>
        <dl className="grid grid-cols-2 gap-3 rounded-md bg-bg-page p-3 font-ui text-caption">
          <div>
            <dt className="text-text-muted">Cooldown</dt>
            <dd className="text-text-primary">{formatSeconds(rule.cooldown_seconds)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">每日上限</dt>
            <dd className="text-text-primary">{rule.daily_cap} 次</dd>
          </div>
          <div>
            <dt className="text-text-muted">产出类型</dt>
            <dd className="text-text-primary">
              {ASSET_TYPE_LABEL[rule.asset_type] ?? rule.asset_type}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">优先级</dt>
            <dd className="text-text-primary">{rule.priority}</dd>
          </div>
        </dl>
      </section>

      {/* 触发历史 */}
      <section className="mt-6 space-y-2">
        <h3 className="flex items-center gap-2 font-ui text-eyebrow uppercase text-text-muted">
          <History className="size-3" />
          最近触发
        </h3>
        {executionsQuery.isLoading ? (
          <LoadingSkeleton variant="list" />
        ) : (executionsQuery.data ?? []).length === 0 ? (
          <p className="rounded-md bg-bg-page p-3 text-center text-caption text-text-subtle">
            还没有触发历史
          </p>
        ) : (
          <ul className="space-y-1.5">
            {(executionsQuery.data ?? []).map((exe) => (
              <ExecutionRow key={exe.id} execution={exe} />
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

// ──────────────────────────────────────────────────────────


function ExecutionRow({ execution: e }: { execution: TriggerExecution }) {
  const statusMeta = {
    scheduled: { label: '撤回窗口中', icon: Loader2, cls: 'text-info' },
    fired: { label: '已触发', icon: CheckCircle2, cls: 'text-success-dark' },
    canceled: { label: '已取消', icon: XCircle, cls: 'text-text-muted' },
    skipped: { label: '已跳过', icon: XCircle, cls: 'text-text-muted' },
    failed: { label: '失败', icon: XCircle, cls: 'text-danger' },
    expired: { label: '已过期', icon: XCircle, cls: 'text-text-muted' },
  }[e.status]
  const Icon = statusMeta.icon
  return (
    <li className="flex items-start gap-3 rounded-md bg-bg-page p-3 text-caption">
      <Icon className={cn('size-3.5 shrink-0 mt-0.5', statusMeta.cls)} />
      <div className="flex-1 space-y-0.5">
        <p className="flex items-center gap-2 text-text-primary">
          <span className="font-medium">{statusMeta.label}</span>
          {e.skip_reason && <span className="text-text-muted">· {e.skip_reason}</span>}
        </p>
        <p className="text-text-muted">{e.signal.summary}</p>
        <p className="text-text-subtle font-mono text-micro">{e.created_at.slice(0, 16)}</p>
      </div>
    </li>
  )
}

// ──────────────────────────────────────────────────────────
// T35 引导向导卡片
// ──────────────────────────────────────────────────────────


interface OnboardingCardProps {
  projectId: string | undefined
  rules: TriggerRule[]
  selected: Set<string>
  onToggle: (id: string) => void
}

function OnboardingCard({ projectId, rules, selected, onToggle }: OnboardingCardProps) {
  const qc = useQueryClient()
  const enableMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        `/projects/${projectId}/auto-triggers/onboarding`,
        { enabled_rule_ids: Array.from(selected) },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auto-trigger', projectId, 'rules'] })
    },
  })

  // 默认推荐勾选 (除 book, Q4 决策)
  const recommendedIds = rules
    .filter((r) => r.asset_type !== 'book')
    .map((r) => r.id)
  const effectiveSelected = selected.size > 0 ? selected : new Set(recommendedIds)

  return (
    <div className="rounded-md border border-accent-primary bg-accent-primary-light/30 p-5 space-y-4">
      <div className="flex items-start gap-3">
        <Sparkles className="mt-0.5 size-5 text-accent-primary-dark" />
        <div className="flex-1">
          <h3 className="font-content text-h3 text-text-primary">启用自动触发？</h3>
          <p className="mt-1 text-body-sm text-text-secondary">
            TokenKnows 可基于研发过程信号自动产出文档。下面是为你预选的 4 条最常用规则。
          </p>
        </div>
      </div>
      <ul className="space-y-2">
        {rules.map((rule) => {
          const ModeIcon = MODE_META[rule.mode].icon
          const checked = effectiveSelected.has(rule.id)
          return (
            <li key={rule.id}>
              <label className="flex items-start gap-3 rounded-md bg-bg-card p-3 cursor-pointer hover:bg-bg-warm">
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onToggle(rule.id)}
                  className="mt-0.5"
                />
                <div className="flex-1 space-y-0.5">
                  <p className="flex items-center gap-2">
                    <ModeIcon className={cn('size-3.5', MODE_META[rule.mode].tint)} />
                    <span className="font-ui text-body-sm font-medium text-text-primary">
                      {rule.name}
                    </span>
                    {rule.asset_type === 'book' && (
                      <Badge variant="outline" className="font-ui text-micro text-warning">
                        token 用量大
                      </Badge>
                    )}
                  </p>
                  <p className="text-caption text-text-muted">{rule.description}</p>
                </div>
              </label>
            </li>
          )
        })}
      </ul>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" disabled={enableMutation.isPending}>
          稍后再说
        </Button>
        <Button
          onClick={() => enableMutation.mutate()}
          disabled={enableMutation.isPending}
        >
          {enableMutation.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Cog className="size-3.5" />
          )}
          启用选中
        </Button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────
// 工具函数
// ──────────────────────────────────────────────────────────


function describeCron(expr: string): string {
  // 极简翻译, 命中常见预置规则即可
  const map: Record<string, string> = {
    '0 9 * * 1': '每周一 09:00',
    '0 9 * * *': '每天 09:00',
    '0 0 1 * *': '每月 1 日 00:00',
    '0 3 * * *': '每天 03:00',
  }
  return map[expr] ?? expr
}

function formatSeconds(s: number): string {
  if (s >= 86400) return `${Math.round(s / 86400)} 天`
  if (s >= 3600) return `${Math.round(s / 3600)} 小时`
  if (s >= 60) return `${Math.round(s / 60)} 分钟`
  return `${s} 秒`
}


// ──────────────────────────────────────────────────────────
// v0.4.4 月配额仪表盘 (体验要素 #32)
// ──────────────────────────────────────────────────────────


function QuotaCard({ projectId }: { projectId: string | undefined }) {
  const qc = useQueryClient()
  const quotaQuery = useQuery({
    queryKey: ['auto-trigger', projectId, 'quota'],
    queryFn: async (): Promise<QuotaResponse> => {
      const { data } = await api.get(
        `/projects/${projectId}/auto-triggers/quota`,
      )
      return data
    },
    enabled: Boolean(projectId),
    refetchInterval: 30_000, // 30s 自动刷新, 让记账实时可见
  })

  const unthrottle = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(
        `/projects/${projectId}/auto-triggers/quota`,
        { is_throttled: false },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auto-trigger', projectId, 'quota'] })
    },
  })

  if (quotaQuery.isLoading || !quotaQuery.data) return null
  const q = quotaQuery.data
  const pct = Math.min(q.usage_ratio * 100, 100)
  const stateMeta = {
    healthy: { label: '正常', cls: 'text-success-dark', bar: 'bg-success-dark', icon: CheckCircle2 },
    warning: { label: '即将耗尽', cls: 'text-warning', bar: 'bg-warning', icon: AlertTriangle },
    throttled: { label: '已暂停', cls: 'text-danger', bar: 'bg-danger', icon: ShieldOff },
  }[q.status]
  const Icon = stateMeta.icon

  return (
    <div
      className={cn(
        'rounded-md border bg-bg-card p-4 space-y-3',
        q.status === 'throttled'
          ? 'border-danger'
          : q.status === 'warning'
          ? 'border-warning'
          : 'border-border-subtle',
      )}
      aria-label="月配额仪表盘"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={cn('size-4', stateMeta.cls)} />
          <span className="font-ui text-body font-medium text-text-primary">
            本月 LLM 配额 · {q.year_month}
          </span>
          <Badge variant="outline" className={cn('font-ui text-micro', stateMeta.cls)}>
            {stateMeta.label}
          </Badge>
        </div>
        {q.is_throttled && (
          <Button
            size="sm"
            variant="outline"
            disabled={unthrottle.isPending}
            onClick={() => unthrottle.mutate()}
            className="font-ui text-caption"
          >
            {unthrottle.isPending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <ShieldOff className="size-3" />
            )}
            紧急放行
          </Button>
        )}
      </div>

      {/* 进度条 */}
      <div>
        <div className="flex justify-between font-ui text-caption text-text-muted mb-1">
          <span>
            {formatTokens(q.tokens_used)} / {formatTokens(q.monthly_token_limit)} tokens
          </span>
          <span className={stateMeta.cls}>{pct.toFixed(1)}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-bg-warm">
          <div
            className={cn('h-full transition-all', stateMeta.bar)}
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
      </div>

      <div className="flex items-center gap-4 font-ui text-caption text-text-muted">
        <span>已生成 {q.auto_gen_count} 份</span>
        <span>·</span>
        <span>每日上限 {q.daily_auto_gen_limit} 份</span>
        {q.status === 'warning' && (
          <span className="ml-auto text-warning">
            ⚠ 用量已达 80%; 建议复核规则或调整月配额
          </span>
        )}
        {q.status === 'throttled' && (
          <span className="ml-auto text-danger font-medium">
            🛑 自动触发已暂停 (含 LLM 用量)
          </span>
        )}
      </div>
    </div>
  )
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}
