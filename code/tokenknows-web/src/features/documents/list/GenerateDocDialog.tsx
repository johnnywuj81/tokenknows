/**
 * GenerateDocDialog · "生成新文档" dialog
 *
 * 决策 (TaskTechDesign T05):
 *   - "生成新文档"按钮触发 dialog, **不是**跳到新页面;
 *   - dialog 内选类型 + 时间窗 + 源 filter + LLM 模型;
 *   - 提交后立刻 close + 列表卡进入"生成中"状态。
 *
 * MVP: 模型 allowlist 硬编码,T14 接 GET /llm/models 后由后端驱动。
 */

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useGenerateAsset } from '../hooks/useGenerateAsset'
import { isApiError } from '@/lib/api'
import type { AssetType } from '@/types/api'

interface GenerateDocDialogProps {
  projectId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const TYPES: { value: AssetType; label: string; description: string }[] = [
  {
    value: 'weekly_report',
    label: '项目周报',
    description: '本周进展 / Bug / 决策 / 风险 / 下周计划五段',
  },
  {
    value: 'tech_design',
    label: '技术方案',
    description: '基于设计讨论生成 6 部分技术方案',
  },
  { value: 'adr', label: 'ADR', description: '从架构决策事件识别 → 5 部分记录' },
  {
    value: 'incident',
    label: '问题复盘',
    description: '从 Bug 与故障事件生成 6 部分复盘',
  },
  {
    value: 'book',
    label: '技术书籍',
    description: 'v0.2 · 卷-章-节嵌套大纲, 10 万字+ 长文档',
  },
  {
    value: 'agent_skill',
    label: 'Agent 专家技能',
    description: 'v0.2 · 从已批准章节蒸馏可复用 skill (建议改用 /skills 页面)',
  },
]

const WINDOWS = [
  { value: 'this_week', label: '本周' },
  { value: 'last_week', label: '上周' },
  { value: 'last_7_days', label: '最近 7 天' },
  { value: 'last_14_days', label: '最近 14 天' },
  { value: 'last_30_days', label: '最近 30 天' },
]

const MODELS = [
  { value: 'auto', label: '自动选择(推荐)' },
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 · 云端' },
  { value: 'gpt-4o', label: 'GPT-4o · 云端' },
  { value: 'qwen2.5-32b', label: 'Qwen2.5-32B · 本地' },
]

export function GenerateDocDialog({
  projectId,
  open,
  onOpenChange,
}: GenerateDocDialogProps) {
  const [type, setType] = useState<AssetType>('weekly_report')
  const [timeWindow, setTimeWindow] = useState('this_week')
  const [model, setModel] = useState('auto')
  const generate = useGenerateAsset()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    generate.mutate(
      {
        projectId,
        type,
        time_window: timeWindow,
        model_override: model === 'auto' ? undefined : model,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
        },
      },
    )
  }

  const errorMessage = isApiError(generate.error) ? generate.error.message : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-content">生成新文档</DialogTitle>
          <DialogDescription>
            选择文档类型与时间范围。生成完成后会出现在列表中,通常需要 30-60 秒。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-2">
            <Label className="font-ui">文档类型</Label>
            <RadioGroup
              value={type}
              onValueChange={(v) => setType(v as AssetType)}
              className="grid grid-cols-1 gap-2 sm:grid-cols-2"
            >
              {TYPES.map((t) => (
                <Label
                  key={t.value}
                  htmlFor={`type-${t.value}`}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-border-subtle bg-bg-card p-2.5 has-[[data-state=checked]]:border-accent-primary has-[[data-state=checked]]:bg-accent-primary-light"
                >
                  <RadioGroupItem value={t.value} id={`type-${t.value}`} className="mt-0.5" />
                  <div className="min-w-0">
                    <p className="font-ui text-body-sm font-medium text-text-primary">
                      {t.label}
                    </p>
                    <p className="line-clamp-1 text-caption text-text-muted">{t.description}</p>
                  </div>
                </Label>
              ))}
            </RadioGroup>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="time-window" className="font-ui">时间范围</Label>
              <Select value={timeWindow} onValueChange={setTimeWindow}>
                <SelectTrigger id="time-window" className="font-ui text-body-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WINDOWS.map((w) => (
                    <SelectItem key={w.value} value={w.value} className="font-ui">
                      {w.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="model" className="font-ui">LLM 模型</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger id="model" className="font-ui text-body-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODELS.map((m) => (
                    <SelectItem key={m.value} value={m.value} className="font-ui">
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {errorMessage ? (
            <div
              className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
              role="alert"
            >
              {errorMessage}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="font-ui"
              disabled={generate.isPending}
            >
              取消
            </Button>
            <Button type="submit" className="font-ui" disabled={generate.isPending}>
              {generate.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  提交中...
                </>
              ) : (
                '开始生成'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
