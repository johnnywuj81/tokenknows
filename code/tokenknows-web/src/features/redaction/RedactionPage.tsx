/**
 * T10 · RedactionPage (脱敏确认面板)
 *
 * 流程:
 *   1. 进入页面 → useRedactionScan 读最近一次扫描结果
 *   2. 若 null → 触发 POST /scan (同步扫描, MVP 正则 + 60s timeout)
 *   3. 展示命中项列表 (按 type 分组), 单项确认/豁免
 *   4. 全部处理 → 进入 T11 发布
 *
 * MVP 简化:
 *   - 同步扫描 (后端正则秒返回), 不做 polling
 *   - 单项操作 (批量留 v2)
 *   - 替换占位符硬编码 [REDACTED 风格] (T13 配置化)
 */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ShieldCheck,
  AlertCircle,
  Loader2,
  Mail,
  KeyRound,
  Globe,
  Lock,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useAsset } from '../documents/hooks/useAsset'
import {
  useRedactionScan,
  useTriggerRedactionScan,
  useConfirmRedaction,
  useExemptRedaction,
} from './hooks/useRedaction'
import type { RedactionItem } from '@/types/api'
import { cn } from '@/lib/utils'

export default function RedactionPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>()
  const navigate = useNavigate()
  const assetQuery = useAsset(docId)
  const scanQuery = useRedactionScan(docId)
  const trigger = useTriggerRedactionScan()
  const confirm = useConfirmRedaction()
  const exempt = useExemptRedaction()

  const [exemptTarget, setExemptTarget] = useState<RedactionItem | null>(null)
  const [exemptReason, setExemptReason] = useState('')

  // 进入页面后, 若尚未扫描 (返回 null) → 自动触发一次
  useEffect(() => {
    if (
      !docId ||
      scanQuery.isLoading ||
      scanQuery.data !== null ||
      trigger.isPending ||
      trigger.isSuccess
    ) {
      return
    }
    trigger.mutate(docId)
  }, [docId, scanQuery.isLoading, scanQuery.data, trigger])

  const scanData = scanQuery.data
  const items = useMemo(() => scanData?.items ?? [], [scanData])
  const grouped = useMemo(() => groupByType(items), [items])
  const pendingCount = items.filter((i) => i.status === 'pending').length
  const totalCount = items.length

  function handleConfirm(item: RedactionItem) {
    if (!docId) return
    confirm.mutate({ assetId: docId, itemIds: [item.id] })
  }

  function handleExemptSubmit() {
    if (!docId || !exemptTarget) return
    const trimmed = exemptReason.trim()
    if (trimmed.length < 3) return
    exempt.mutate(
      { assetId: docId, itemId: exemptTarget.id, reason: trimmed },
      {
        onSuccess: () => {
          setExemptTarget(null)
          setExemptReason('')
        },
      },
    )
  }

  const isInitialLoading =
    assetQuery.isLoading || scanQuery.isLoading || trigger.isPending
  const error = assetQuery.error ?? scanQuery.error ?? trigger.error

  if (error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="脱敏扫描失败"
        error={error}
        onRetry={() => {
          assetQuery.refetch()
          scanQuery.refetch()
          if (docId) trigger.mutate(docId)
        }}
        action={
          <button
            type="button"
            onClick={() => projectId && navigate(`/projects/${projectId}/documents/${docId}`)}
            className="font-ui text-body-sm text-accent-primary-dark hover:underline"
          >
            返回文档
          </button>
        }
      />
    )
  }

  if (isInitialLoading || !assetQuery.data) {
    return <LoadingSkeleton variant="document" />
  }

  const asset = assetQuery.data

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto]">
      <header className="flex items-center justify-between border-b border-border-subtle bg-bg-card px-6 py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => projectId && navigate(`/projects/${projectId}/documents/${docId}`)}
            className="font-ui text-caption text-text-muted hover:text-text-primary"
          >
            ← 返回文档
          </button>
          <h1 className="font-content text-h3 text-text-primary">
            脱敏确认 · {asset.title}
          </h1>
          <RedactionStateBadge state={asset.redaction_state} />
        </div>
        <div className="font-ui text-caption text-text-muted">
          命中 {totalCount} 项 · 待处理 {pendingCount} 项
        </div>
      </header>

      <main className="overflow-auto bg-bg-page px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {items.length === 0 ? (
            <EmptyState
              icon={<ShieldCheck className="size-8 text-success-dark" />}
              title="未命中敏感内容"
              description="本文档章节内容已通过 PII / Token / 内部代号 / IP 等正则扫描, 可直接进入发布。"
              action={{
                label: '进入发布 (T11)',
                onClick: () => {
                  if (!projectId || !docId) return
                  useDocumentUiStore.getState().openPublish()
                  navigate(`/projects/${projectId}/documents/${docId}`)
                },
              }}
            />
          ) : (
            grouped.map(({ type, items: typeItems }) => (
              <section key={type}>
                <header className="mb-2 flex items-center gap-2">
                  <TypeIcon type={type} />
                  <h2 className="font-content text-h3 text-text-primary">
                    {TYPE_LABEL[type] ?? type}
                  </h2>
                  <span className="font-ui text-caption text-text-muted">
                    {typeItems.length} 项
                  </span>
                </header>
                <ul className="space-y-2">
                  {typeItems.map((item) => (
                    <li
                      key={item.id}
                      className={cn(
                        'rounded-md border bg-bg-card p-3',
                        item.status === 'confirmed'
                          ? 'border-success-border bg-success-bg/30'
                          : item.status === 'exempted'
                            ? 'border-warning-border bg-warning-bg/30'
                            : 'border-border-subtle',
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <code className="rounded bg-bg-warm px-1.5 py-0.5 font-mono text-caption text-text-primary">
                              {item.matched_text}
                            </code>
                            <StatusBadge status={item.status} />
                          </div>
                          {item.context_before || item.context_after ? (
                            <p className="font-content text-body-sm text-text-muted leading-relaxed">
                              <span className="text-text-subtle">…{item.context_before}</span>
                              <mark className="rounded bg-warning-bg/60 px-0.5 text-text-primary">
                                {item.matched_text}
                              </mark>
                              <span className="text-text-subtle">{item.context_after}…</span>
                            </p>
                          ) : null}
                          <p className="font-ui text-micro text-text-subtle">
                            建议替换为{' '}
                            <code className="font-mono">{item.suggested_replacement}</code>
                            {item.reason ? (
                              <>
                                {' '}· 豁免理由: <em>{item.reason}</em>
                              </>
                            ) : null}
                          </p>
                        </div>
                        {item.status === 'pending' ? (
                          <div className="flex flex-col gap-1.5">
                            <Button
                              type="button"
                              size="sm"
                              disabled={confirm.isPending}
                              onClick={() => handleConfirm(item)}
                              className="font-ui text-caption"
                            >
                              {confirm.isPending &&
                              confirm.variables?.itemIds.includes(item.id) ? (
                                <Loader2 className="size-3 animate-spin" />
                              ) : (
                                <CheckCircle2 className="size-3" />
                              )}
                              脱敏
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={exempt.isPending}
                              onClick={() => {
                                setExemptTarget(item)
                                setExemptReason('')
                              }}
                              className="font-ui text-caption text-warning hover:bg-warning-bg/40"
                            >
                              <XCircle className="size-3" />
                              豁免
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </main>

      <footer className="flex items-center justify-between gap-3 border-t border-border-subtle bg-bg-card px-6 py-3">
        <div className="font-ui text-caption text-text-muted">
          {totalCount === 0
            ? '无命中敏感内容'
            : `处理进度: ${totalCount - pendingCount} / ${totalCount}`}
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => docId && trigger.mutate(docId)}
            disabled={trigger.isPending}
            className="font-ui text-caption"
          >
            {trigger.isPending ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                重新扫描中
              </>
            ) : (
              '重新扫描'
            )}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={pendingCount > 0}
            onClick={() => {
              if (!projectId || !docId) return
              useDocumentUiStore.getState().openPublish()
              navigate(`/projects/${projectId}/documents/${docId}`)
            }}
            className="font-ui text-caption"
          >
            进入发布 (T11)
          </Button>
        </div>
      </footer>

      <Dialog
        open={exemptTarget !== null}
        onOpenChange={(o) => {
          if (!o && !exempt.isPending) {
            setExemptTarget(null)
            setExemptReason('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-content">
              <XCircle className="size-4 text-warning" />
              豁免脱敏
            </DialogTitle>
            <DialogDescription className="font-ui text-caption text-text-muted">
              豁免意味着该项保留原文不脱敏。理由会进审计日志 (T14 可查).
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            {exemptTarget ? (
              <p className="rounded-md border border-border-subtle bg-bg-warm/40 p-2 font-ui text-caption text-text-secondary">
                命中: <code className="font-mono">{exemptTarget.matched_text}</code>{' '}
                ({TYPE_LABEL[exemptTarget.type] ?? exemptTarget.type})
              </p>
            ) : null}
            <label
              htmlFor="exempt-reason"
              className="font-ui text-caption font-medium text-text-secondary"
            >
              豁免理由 <span className="text-danger">*</span>
            </label>
            <textarea
              id="exempt-reason"
              value={exemptReason}
              onChange={(e) => setExemptReason(e.target.value)}
              disabled={exempt.isPending}
              placeholder="说明为何此项不需要脱敏 (≥3 字符)"
              rows={3}
              className="w-full resize-none rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary placeholder:text-text-subtle focus:border-accent-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
            <p className="font-ui text-micro text-text-subtle">
              至少 3 个字符. 当前 {exemptReason.trim().length} 字符.
            </p>
            {exempt.error ? (
              <div className="flex items-start gap-1.5 rounded-md border border-danger-border bg-danger-bg px-2 py-1.5 text-danger">
                <AlertCircle className="size-3.5 mt-0.5 shrink-0" />
                <p className="font-ui text-caption">豁免失败, 请重试.</p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={exempt.isPending}
              onClick={() => {
                setExemptTarget(null)
                setExemptReason('')
              }}
              className="font-ui"
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={exempt.isPending || exemptReason.trim().length < 3}
              onClick={handleExemptSubmit}
              className="font-ui"
            >
              {exempt.isPending ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  豁免中…
                </>
              ) : (
                '确认豁免'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

const TYPE_LABEL: Record<string, string> = {
  EMAIL: '邮箱地址',
  API_KEY: 'API 密钥',
  IP: 'IP 地址',
  INTERNAL: '内部代号',
  CUSTOMER: '客户名称',
}

interface TypeIconProps {
  type: string
}

function TypeIcon({ type }: TypeIconProps) {
  const className = 'size-4 text-text-secondary'
  switch (type) {
    case 'EMAIL':
      return <Mail className={className} />
    case 'API_KEY':
      return <KeyRound className={className} />
    case 'IP':
      return <Globe className={className} />
    case 'INTERNAL':
    case 'CUSTOMER':
      return <Lock className={className} />
    default:
      return <ShieldCheck className={className} />
  }
}

interface Group {
  type: string
  items: RedactionItem[]
}

function groupByType(items: RedactionItem[]): Group[] {
  const map = new Map<string, RedactionItem[]>()
  for (const it of items) {
    const arr = map.get(it.type)
    if (arr) arr.push(it)
    else map.set(it.type, [it])
  }
  return [...map.entries()].map(([type, arr]) => ({ type, items: arr }))
}

interface RedactionStateBadgeProps {
  state: 'any_unresolved' | 'all_confirmed'
}

function RedactionStateBadge({ state }: RedactionStateBadgeProps) {
  return state === 'all_confirmed' ? (
    <span className="rounded-full bg-success-bg px-2 py-0.5 font-ui text-micro text-success-dark">
      已脱敏
    </span>
  ) : (
    <span className="rounded-full bg-warning-bg px-2 py-0.5 font-ui text-micro text-warning">
      待确认
    </span>
  )
}

interface StatusBadgeProps {
  status: RedactionItem['status']
}

function StatusBadge({ status }: StatusBadgeProps) {
  const map = {
    pending: { label: '待处理', cls: 'bg-bg-warm text-text-muted' },
    confirmed: { label: '已脱敏', cls: 'bg-success-bg text-success-dark' },
    exempted: { label: '已豁免', cls: 'bg-warning-bg text-warning' },
    overridden: { label: '已覆盖', cls: 'bg-info-bg text-info' },
  } as const
  const { label, cls } = map[status]
  return (
    <span className={cn('rounded-full px-1.5 py-0.5 font-ui text-micro', cls)}>
      {label}
    </span>
  )
}
