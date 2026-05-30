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
import { Input } from '@/components/ui/input'
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
    description: '蒸馏一份可执行的 SKILL.md (Anthropic 风格), 需要主题',
  },
  {
    value: 'knowledge_graph',
    label: '知识图谱',
    description: 'v1.2 · 实体关系图谱; 4 类节点 + 6 类边, 跨文档实体合并',
  },
]

const WINDOWS = [
  { value: 'this_week', label: '本周' },
  { value: 'last_week', label: '上周' },
  { value: 'last_7_days', label: '最近 7 天' },
  { value: 'last_14_days', label: '最近 14 天' },
  { value: 'last_30_days', label: '最近 30 天' },
]

// T106 · 每个 model 显式标 provider, 避免 anthropic+gpt-4o 错配
const MODELS: { value: string; label: string; provider?: string }[] = [
  { value: 'auto', label: '自动选择(推荐)' },
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 · 云端', provider: 'anthropic' },
  { value: 'gpt-4o', label: 'GPT-4o · 云端', provider: 'openai' },
  { value: 'abab6.5s-chat', label: 'MiniMax abab6.5s · 云端', provider: 'minimax' },
  { value: 'qwen2.5:3b', label: 'Qwen2.5 3B · Ollama 本地', provider: 'ollama' },
]

export function GenerateDocDialog({
  projectId,
  open,
  onOpenChange,
}: GenerateDocDialogProps) {
  const [type, setType] = useState<AssetType>('weekly_report')
  const [timeWindow, setTimeWindow] = useState('this_week')
  const [model, setModel] = useState('auto')
  const [topicHint, setTopicHint] = useState('')
  const generate = useGenerateAsset()

  // A 改造 · agent_skill 必须有主题, 否则 LLM 会蒸出"30 天纪事"型废 skill.
  const trimmedTopic = topicHint.trim()
  const topicRequired = type === 'agent_skill'
  const topicMissing = topicRequired && trimmedTopic.length === 0
  const submitDisabled = generate.isPending || topicMissing

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (topicMissing) return
    // T106 · 找到对应 provider, 一并传给后端 (避免 anthropic+gpt-4o 错配)
    const selected = MODELS.find((m) => m.value === model)
    generate.mutate(
      {
        projectId,
        type,
        time_window: timeWindow,
        model_override: model === 'auto' ? undefined : model,
        provider_override: model === 'auto' ? undefined : selected?.provider,
        topic_hint: trimmedTopic ? trimmedTopic : undefined,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
          // 关闭后清理本地 state, 下次再打开时是干净表单
          setTopicHint('')
        },
      },
    )
  }

  const errorMessage = isApiError(generate.error) ? generate.error.message : null
  const errorStatus = isApiError(generate.error) ? generate.error.status : null

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

          {/* A 改造 · 主题提示: 所有类型都可填, agent_skill 必填.
                 - agent_skill: 决定 SKILL.md 的范围 + 名字
                 - 其它类型: 在 collect 阶段对 events 做关键词预过滤 */}
          <div className="space-y-1.5">
            <Label htmlFor="topic-hint" className="font-ui">
              主题 / 关键词
              {topicRequired ? (
                <span className="ml-1 text-danger" aria-hidden>*</span>
              ) : (
                <span className="ml-1 text-text-muted text-caption">(可选)</span>
              )}
            </Label>
            <Input
              id="topic-hint"
              value={topicHint}
              onChange={(e) => setTopicHint(e.target.value)}
              placeholder={
                type === 'agent_skill'
                  ? '例: PR review 风格 / docker 部署 / 故障复盘'
                  : '可空 · 仅按时间窗范围生成'
              }
              maxLength={200}
              className="font-ui text-body-sm"
              aria-invalid={topicMissing}
              aria-describedby="topic-hint-help"
            />
            <p id="topic-hint-help" className="text-caption text-text-muted">
              {type === 'agent_skill'
                ? '蒸馏出的 SKILL.md 将围绕该主题 (必填)'
                : '提供主题后, 收集阶段会按关键词过滤 events'}
            </p>
          </div>

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
              data-testid="generate-error"
            >
              <div className="flex items-start justify-between gap-2">
                <strong className="font-ui">⚠️ 生成失败</strong>
                {errorStatus !== null ? (
                  <span className="font-mono text-caption text-text-muted">
                    {errorStatus === 0 ? '网络错误' : `HTTP ${errorStatus}`}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-caption">{errorMessage}</p>
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
            <Button type="submit" className="font-ui" disabled={submitDisabled}>
              {generate.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  提交中...
                </>
              ) : topicMissing ? (
                '请填写主题'
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
