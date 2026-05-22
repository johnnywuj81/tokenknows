/**
 * v0.4 体验要素 #30 · 撤回窗口浮动通知卡.
 *
 * 挂在 AppLayout 顶层 (全局); polling 当前项目下 status=scheduled 的执行,
 * 显示倒计时 + 取消按钮.
 *
 * 设计:
 * - 右下角浮动 (不阻塞主内容)
 * - 多条聚合 (e.g. "5 分钟后将生成 3 份文档"); 但展开后逐条显示
 * - 倒计时每秒减一; < 30s 变橙色, < 10s 变红色
 * - 取消按钮: 调 cancel API, optimistic UI 立即变红 "已取消" 2s 后消失
 *
 * 不做 (留 v0.4.1):
 * - SSE 实时推送 (现在用 3s polling, 体验已可接受)
 * - "聚合卡 → 展开" 二级 UI (单条直接显示)
 */

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, X, Clock, CheckCircle2, AlertCircle } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { useProjectStore } from '@/stores/projectStore'
import { cn } from '@/lib/utils'
import type { TriggerExecution } from '@/types/api'

const POLL_INTERVAL_MS = 3000

export function WithdrawNotification() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId)

  const query = useQuery({
    queryKey: ['auto-trigger', currentProjectId, 'executions', { status: 'scheduled' }],
    queryFn: async (): Promise<TriggerExecution[]> => {
      const { data } = await api.get(
        `/projects/${currentProjectId}/auto-triggers/executions?status=scheduled&limit=10`,
      )
      return data.data ?? []
    },
    enabled: Boolean(currentProjectId),
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  })

  const scheduled = query.data ?? []
  if (scheduled.length === 0) return null

  return (
    <div
      className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2"
      aria-label="待生成文档通知"
    >
      {scheduled.map((exe) => (
        <NotificationCard
          key={exe.id}
          execution={exe}
          projectId={currentProjectId ?? ''}
        />
      ))}
    </div>
  )
}

// ──────────────────────────────────────────────────────────


interface NotificationCardProps {
  execution: TriggerExecution
  projectId: string
}

function NotificationCard({ execution, projectId }: NotificationCardProps) {
  const qc = useQueryClient()
  const [dismissed, setDismissed] = useState(false)

  const fireAtMs = useMemo(
    () => new Date(execution.fire_at).getTime(),
    [execution.fire_at],
  )
  const [secondsLeft, setSecondsLeft] = useState(() =>
    Math.max(0, Math.floor((fireAtMs - Date.now()) / 1000)),
  )

  useEffect(() => {
    const id = setInterval(() => {
      const left = Math.max(0, Math.floor((fireAtMs - Date.now()) / 1000))
      setSecondsLeft(left)
      if (left === 0) clearInterval(id)
    }, 1000)
    return () => clearInterval(id)
  }, [fireAtMs])

  const cancelMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        `/projects/${projectId}/auto-triggers/executions/${execution.id}/cancel`,
      )
      return data as TriggerExecution
    },
    onSuccess: () => {
      // 立即从 scheduled 列表移除
      qc.invalidateQueries({
        queryKey: ['auto-trigger', projectId, 'executions'],
      })
      setTimeout(() => setDismissed(true), 1500)
    },
  })

  if (dismissed) return null

  // 颜色阈值
  const urgent = secondsLeft <= 10
  const warning = !urgent && secondsLeft <= 30
  const fired = secondsLeft === 0 && !cancelMutation.isSuccess
  const canceled = cancelMutation.isSuccess

  const containerCls = cn(
    'pointer-events-auto w-[360px] rounded-md border bg-bg-card p-4 font-ui text-body-sm shadow-elev-3',
    canceled && 'border-text-muted opacity-70',
    fired && 'border-success-dark bg-success-bg',
    urgent && !canceled && !fired && 'border-danger',
    warning && !canceled && !fired && 'border-warning',
    !urgent && !warning && !canceled && !fired && 'border-accent-primary',
  )

  return (
    <div className={containerCls} role="status" aria-live="polite">
      <div className="flex items-start gap-2">
        <Bot
          className={cn(
            'mt-0.5 size-4 shrink-0',
            canceled
              ? 'text-text-muted'
              : fired
              ? 'text-success-dark'
              : urgent
              ? 'text-danger'
              : warning
              ? 'text-warning'
              : 'text-accent-primary-dark',
          )}
        />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-text-primary">
            {canceled
              ? '已取消'
              : fired
              ? '已生成'
              : '即将自动生成'}
          </p>
          <p className="line-clamp-2 text-caption text-text-secondary">
            {execution.signal.summary}
          </p>
          {!canceled && !fired && (
            <div className="mt-2 flex items-center gap-2 text-caption">
              <Clock
                className={cn(
                  'size-3.5',
                  urgent
                    ? 'text-danger'
                    : warning
                    ? 'text-warning'
                    : 'text-text-muted',
                )}
              />
              <span
                className={cn(
                  'font-mono tabular-nums',
                  urgent
                    ? 'text-danger font-medium'
                    : warning
                    ? 'text-warning font-medium'
                    : 'text-text-secondary',
                )}
              >
                {formatCountdown(secondsLeft)}
              </span>
              <span className="text-text-subtle">后开始</span>
            </div>
          )}
          {canceled && (
            <p className="mt-1 flex items-center gap-1 text-caption text-text-muted">
              <CheckCircle2 className="size-3" />
              LLM 已被阻止调用 · 无 token 消耗
            </p>
          )}
          {fired && (
            <p className="mt-1 flex items-center gap-1 text-caption text-success-dark">
              <CheckCircle2 className="size-3" />
              撤回窗口已过 · LLM 调用进行中
            </p>
          )}
          {cancelMutation.isError && (
            <p className="mt-1 flex items-center gap-1 text-caption text-danger">
              <AlertCircle className="size-3" />
              撤回失败 · 可能已过窗口
            </p>
          )}
        </div>
        {!canceled && !fired && (
          <Button
            variant="ghost"
            size="sm"
            disabled={cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
            className="font-ui text-caption shrink-0 -mt-1 -mr-1"
          >
            <X className="size-3" />
            取消
          </Button>
        )}
      </div>
    </div>
  )
}

function formatCountdown(s: number): string {
  if (s <= 0) return '0:00'
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${String(r).padStart(2, '0')}`
}
