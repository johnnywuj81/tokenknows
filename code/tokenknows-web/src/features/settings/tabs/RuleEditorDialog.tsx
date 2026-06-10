/**
 * v0.4.3 T43 · RuleEditorDialog (builder 模板).
 *
 * 新建 / 编辑触发规则; 不开放自由 DSL, 按 mode 切换字段:
 * - cron: cron_expr (含 plain English 翻译) + extra_condition
 * - event: event_type select + label_any (逗号分隔)
 * - threshold: metric select + comparator + value
 *
 * v0.4.3 简化:
 * - 仅新建 (POST). 编辑留 v0.4.4 (UI 复杂度大, 涉及"修改后旧 scheduled 怎么办" 决策)
 * - 不支持自定义 metric / event_type (仅下拉预设)
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import type { TriggerMode, TriggerRule } from '@/types/api'

interface RuleEditorDialogProps {
  projectId: string | undefined
  open: boolean
  onOpenChange: (open: boolean) => void
}

const ASSET_TYPES = [
  { value: 'weekly_report', label: '周报' },
  { value: 'tech_design', label: '技术方案' },
  { value: 'adr', label: 'ADR' },
  { value: 'incident', label: '问题复盘' },
  { value: 'book', label: '书籍' },
  { value: 'agent_skill', label: 'Agent Skill' },
] as const

const EVENT_TYPES = [
  { value: 'github_pr_merged', label: 'GitHub PR merged' },
  { value: 'github_pr_opened', label: 'GitHub PR opened' },
  { value: 'github_issue_opened', label: 'GitHub Issue opened' },
  { value: 'github_issue_closed', label: 'GitHub Issue closed' },
] as const

const THRESHOLD_METRICS = [
  { value: 'approved_chapters_total', label: '累积已审批章节数' },
  { value: 'events_count_30d', label: '近 30 天事件数' },
  { value: 'events_count_7d', label: '近 7 天事件数' },
  { value: 'im_signal_count_30d', label: '近 30 天 IM 信号数' },
  { value: 'im_signal_count_7d', label: '近 7 天 IM 信号数' },
] as const

const CRON_PRESETS = [
  { value: '0 9 * * 1', label: '每周一 09:00' },
  { value: '0 9 * * 5', label: '每周五 09:00' },
  { value: '0 9 * * *', label: '每天 09:00' },
  { value: '0 0 1 * *', label: '每月 1 日 00:00' },
  { value: '0 */6 * * *', label: '每 6 小时' },
] as const

// ──────────────────────────────────────────────────────────


export function RuleEditorDialog({
  projectId, open, onOpenChange,
}: RuleEditorDialogProps) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [mode, setMode] = useState<TriggerMode>('cron')
  const [assetType, setAssetType] = useState('weekly_report')
  const [priority, setPriority] = useState(50)
  const [cooldownSec, setCooldownSec] = useState(3600)
  const [dailyCap, setDailyCap] = useState(5)
  const [cronExpr, setCronExpr] = useState('0 9 * * 1')
  const [eventType, setEventType] = useState('github_pr_merged')
  const [labelAny, setLabelAny] = useState('')
  const [thresholdMetric, setThresholdMetric] =
    useState('approved_chapters_total')
  const [thresholdValue, setThresholdValue] = useState(50)

  const reset = () => {
    setName('')
    setDescription('')
    setMode('cron')
    setAssetType('weekly_report')
    setPriority(50)
    setCooldownSec(3600)
    setDailyCap(5)
    setCronExpr('0 9 * * 1')
    setEventType('github_pr_merged')
    setLabelAny('')
    setThresholdMetric('approved_chapters_total')
    setThresholdValue(50)
  }

  const create = useMutation({
    mutationFn: async (): Promise<TriggerRule> => {
      const body: Record<string, unknown> = {
        name: name.trim(),
        description: description.trim(),
        mode, asset_type: assetType,
        priority,
        cooldown_seconds: cooldownSec,
        daily_cap: dailyCap,
        enabled: true,
      }
      if (mode === 'cron') body.cron_expr = cronExpr
      if (mode === 'event') {
        body.event_match = {
          event_type: eventType,
          label_any: labelAny
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
        }
      }
      if (mode === 'threshold') {
        body.threshold_spec = {
          metric: thresholdMetric,
          comparator: '>=',
          value: thresholdValue,
        }
      }
      const { data } = await api.post(
        `/projects/${projectId}/auto-triggers/rules`,
        body,
      )
      return data as TriggerRule
    },
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['auto-trigger', projectId, 'rules'],
      })
      reset()
      onOpenChange(false)
    },
  })

  const canSubmit = name.trim().length > 0 && !create.isPending && (
    mode !== 'cron' || cronExpr.trim().length > 0
  )

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset()
        onOpenChange(o)
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-content text-h3">
            <Plus className="inline size-4 mr-1" />
            新建自动触发规则
          </DialogTitle>
          <DialogDescription>
            创建项目级规则。命中时会有 5 分钟撤回窗口；自动生成的 asset 仍需 Reviewer 审批。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* 名称 */}
          <div className="space-y-1.5">
            <Label htmlFor="name">规则名称 *</Label>
            <Input
              id="name" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例: PR 标 [API-BREAKING] → 自动技术方案"
              maxLength={120}
            />
          </div>

          {/* 描述 */}
          <div className="space-y-1.5">
            <Label htmlFor="desc">描述</Label>
            <Textarea
              id="desc" value={description} rows={2}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="规则意图;给团队解释为什么需要它"
            />
          </div>

          {/* 触发模式 + 类型 (2 列) */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>触发模式</Label>
              <Select value={mode} onValueChange={(v) => setMode(v as TriggerMode)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cron">定时 (cron)</SelectItem>
                  <SelectItem value="event">事件 (event)</SelectItem>
                  <SelectItem value="threshold">阈值 (threshold)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>产出类型</Label>
              <Select value={assetType} onValueChange={setAssetType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ASSET_TYPES.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* mode 专属字段 */}
          {mode === 'cron' && (
            <div className="space-y-1.5">
              <Label>Cron 表达式 *</Label>
              <Select value={cronExpr} onValueChange={setCronExpr}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CRON_PRESETS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      <span className="font-mono mr-2 text-text-muted">
                        {p.value}
                      </span>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                value={cronExpr}
                onChange={(e) => setCronExpr(e.target.value)}
                placeholder="自定义 cron, e.g. 0 9 * * 1"
                className="font-mono"
              />
            </div>
          )}

          {mode === 'event' && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>事件类型</Label>
                <Select value={eventType} onValueChange={setEventType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPES.map((e) => (
                      <SelectItem key={e.value} value={e.value}>
                        {e.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Labels (任一命中即触发)</Label>
                <Input
                  value={labelAny}
                  onChange={(e) => setLabelAny(e.target.value)}
                  placeholder="逗号分隔, e.g. architecture-decision, adr"
                />
                <p className="text-micro text-text-muted">
                  留空 = 不校验 labels (所有该类型事件都触发)
                </p>
              </div>
            </div>
          )}

          {mode === 'threshold' && (
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1.5">
                <Label>指标</Label>
                <Select
                  value={thresholdMetric}
                  onValueChange={setThresholdMetric}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {THRESHOLD_METRICS.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>阈值 (≥)</Label>
                <Input
                  type="number" min={1}
                  value={thresholdValue}
                  onChange={(e) => setThresholdValue(Number(e.target.value))}
                />
              </div>
            </div>
          )}

          {/* 频率限制 */}
          <div className="grid grid-cols-3 gap-3 pt-2 border-t border-border-subtle">
            <div className="space-y-1.5">
              <Label>优先级</Label>
              <Input
                type="number" min={0} max={100}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Cooldown (秒)</Label>
              <Input
                type="number" min={60}
                value={cooldownSec}
                onChange={(e) => setCooldownSec(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>每日上限</Label>
              <Input
                type="number" min={1} max={100}
                value={dailyCap}
                onChange={(e) => setDailyCap(Number(e.target.value))}
              />
            </div>
          </div>

          {create.isError && (
            <div className="rounded-md border border-danger bg-danger-bg/30 px-3 py-2 text-caption text-danger">
              创建失败: {(create.error as Error).message}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={create.isPending}
          >
            取消
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={() => create.mutate()}
          >
            {create.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            创建规则
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
