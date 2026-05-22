/**
 * v0.4 T34 · AutoTriggerBadge + TriggerExplainPopover
 *
 * 挂在 DocHeader 状态徽标旁; 仅当 asset.trigger_meta 非空时渲染.
 *
 * 体验要素:
 * - #33 自动徽标 (与手动生成 asset 区分)
 * - #34 可解释卡 (hover 显示完整信号: rule / signal / confidence / fired_at)
 *
 * 当前不做撤回窗口通知卡 (体验要素 #30) - 需要 SSE + cancel API,
 * 留到 T32 真后端 API 上线后补.
 */

import { Bot } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { AssetTriggerMeta } from '@/types/api'

interface AutoTriggerBadgeProps {
  meta: AssetTriggerMeta
  className?: string
}

const MODE_LABEL: Record<string, string> = {
  cron: '定时触发',
  event: '事件触发',
  threshold: '阈值触发',
  mention: '@机器人触发',
}

export function AutoTriggerBadge({ meta, className }: AutoTriggerBadgeProps) {
  const firedAtLocal = new Date(meta.fired_at).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded bg-info-bg px-1.5 py-0.5 font-ui text-micro font-medium text-info cursor-help',
              className,
            )}
            aria-label={`自动触发 by ${meta.rule_name}`}
          >
            <Bot className="size-3" />
            自动
          </span>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          align="start"
          className="max-w-sm space-y-2 p-3 font-ui text-caption"
        >
          <div className="flex items-center gap-2">
            <Bot className="size-3.5 text-info" />
            <span className="font-medium text-text-primary">
              自动触发 · {MODE_LABEL[meta.trigger_mode] ?? meta.trigger_mode}
            </span>
          </div>
          <dl className="space-y-1">
            <div>
              <dt className="text-text-muted">规则</dt>
              <dd className="text-text-primary">{meta.rule_name}</dd>
            </div>
            <div>
              <dt className="text-text-muted">信号</dt>
              <dd className="text-text-primary">{meta.signal.summary}</dd>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <dt className="text-text-muted">置信度</dt>
                <dd className="text-text-primary">
                  {(meta.confidence * 100).toFixed(0)}%
                </dd>
              </div>
              <div>
                <dt className="text-text-muted">触发时间</dt>
                <dd className="text-text-primary font-mono">{firedAtLocal}</dd>
              </div>
            </div>
          </dl>
          <p className="border-t border-border-subtle pt-2 text-text-subtle">
            自动生成 ≠ 自动发布 · 仍需 Reviewer 审批 (AT-5)
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
