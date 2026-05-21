/**
 * EventDrawer · T04 · 事件详情抽屉
 *
 * 入口: 用户点 EventStream 卡片 → openEventDrawer(event.id)
 *
 * 展示: title / source / author / occurred_at / content / payload (折叠) /
 *       redaction_state badge / trust_score / "在源头打开" 外链
 */

import { useState } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Database,
  Loader2,
  AlertCircle,
  ExternalLink,
  Calendar,
  User as UserIcon,
  Tag,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useEvent } from '../hooks/useEvent'
import type { Event } from '@/types/api'
import { cn } from '@/lib/utils'

export function EventDrawer() {
  const open = useDocumentUiStore((s) => s.eventDrawerOpen)
  const activeId = useDocumentUiStore((s) => s.activeEventId)
  const close = useDocumentUiStore((s) => s.closeEventDrawer)

  // 仅在抽屉打开时 fetch
  const query = useEvent(open ? activeId : null)

  return (
    <Sheet open={open} onOpenChange={(o) => !o && close()}>
      <SheetContent
        side="right"
        className="flex w-[480px] flex-col gap-0 p-0 sm:max-w-[480px]"
      >
        <SheetHeader className="border-b border-border-subtle px-6 py-4">
          <SheetTitle className="flex items-center gap-2 font-content text-h3">
            <Database className="size-4" />
            事件详情
          </SheetTitle>
          <SheetDescription className="font-ui text-caption text-text-muted">
            原始研发事件 · 可作为 ValueSegment 来源
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {query.isLoading ? (
            <DrawerLoading />
          ) : query.error ? (
            <DrawerError onRetry={() => query.refetch()} />
          ) : query.data ? (
            <EventDetail event={query.data} />
          ) : (
            <p className="font-ui text-caption text-text-muted">未选择事件</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

interface EventDetailProps {
  event: Event
}

function EventDetail({ event }: EventDetailProps) {
  const [payloadOpen, setPayloadOpen] = useState(false)
  const occurred = formatDateTime(event.occurred_at)
  const ingested = formatDateTime(event.ingested_at)
  const sourceLabel = SOURCE_LABEL[event.source_type] ?? event.source_type

  return (
    <div className="space-y-5">
      {/* 标题 + 来源 */}
      <header className="space-y-2">
        <div className="flex items-center gap-1.5 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          <Tag className="size-3" />
          <span>{sourceLabel}</span>
          <span className="text-text-subtle">·</span>
          <span className="font-mono text-text-subtle">{event.source_ref}</span>
        </div>
        <h2 className="font-content text-h3 text-text-primary leading-snug">
          {event.title ?? EVENT_TYPE_LABEL[event.event_type] ?? '(无标题)'}
        </h2>
        {event.is_private ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 font-ui text-micro text-warning">
            <ShieldAlert className="size-3" />
            敏感来源 · 内容遮蔽
          </span>
        ) : null}
      </header>

      {/* meta grid */}
      <dl className="grid grid-cols-2 gap-3 font-ui text-caption">
        <div>
          <dt className="font-ui text-micro uppercase tracking-wider text-text-subtle">
            作者
          </dt>
          <dd className="mt-0.5 flex items-center gap-1 text-text-secondary">
            <UserIcon className="size-3 text-text-subtle" />
            <span>{event.author?.name ?? '未知'}</span>
          </dd>
          {event.author?.email ? (
            <dd className="mt-0.5 font-mono text-micro text-text-subtle">
              {event.author.email}
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="font-ui text-micro uppercase tracking-wider text-text-subtle">
            发生时间
          </dt>
          <dd className="mt-0.5 flex items-center gap-1 text-text-secondary">
            <Calendar className="size-3 text-text-subtle" />
            <span>{occurred}</span>
          </dd>
          <dd className="mt-0.5 font-mono text-micro text-text-subtle">
            采集于 {ingested}
          </dd>
        </div>
        <div>
          <dt className="font-ui text-micro uppercase tracking-wider text-text-subtle">
            事件类型
          </dt>
          <dd className="mt-0.5 font-mono text-text-secondary">
            {EVENT_TYPE_LABEL[event.event_type] ?? event.event_type}
          </dd>
        </div>
        <div>
          <dt className="font-ui text-micro uppercase tracking-wider text-text-subtle">
            脱敏状态
          </dt>
          <dd className="mt-0.5">
            <RedactionBadge state={event.redaction_state} />
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="font-ui text-micro uppercase tracking-wider text-text-subtle">
            外部 ID
          </dt>
          <dd className="mt-0.5 font-mono text-text-secondary text-caption">
            {event.external_id || '—'}
          </dd>
        </div>
      </dl>

      {/* trust + tags */}
      <div className="flex flex-wrap items-center gap-2">
        {typeof event.trust_score === 'number' ? (
          <span
            className={cn(
              'rounded-full px-2 py-0.5 font-ui text-micro',
              event.trust_score >= 0.8
                ? 'bg-success-bg text-success-dark'
                : event.trust_score >= 0.5
                  ? 'bg-info-bg text-info'
                  : 'bg-warning-bg text-warning',
            )}
            title={`trust_score=${event.trust_score.toFixed(3)}`}
          >
            TRUST {Math.round(event.trust_score * 100)}
          </span>
        ) : null}
        {event.tags.map((t) => (
          <span
            key={t}
            className="rounded-full bg-bg-warm px-2 py-0.5 font-mono text-micro text-text-secondary"
          >
            {t}
          </span>
        ))}
      </div>

      {/* 原文内容 */}
      <div>
        <p className="font-ui text-micro uppercase tracking-wider text-text-subtle">
          原文
        </p>
        <pre className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-border-subtle bg-bg-warm/40 px-3 py-2 font-content text-body-sm text-text-secondary leading-relaxed">
          {event.content}
        </pre>
      </div>

      {/* payload (折叠) */}
      {event.payload && Object.keys(event.payload).length > 0 ? (
        <div>
          <button
            type="button"
            onClick={() => setPayloadOpen((o) => !o)}
            className="flex w-full items-center gap-1.5 rounded-md font-ui text-micro uppercase tracking-wider text-text-muted hover:text-text-secondary"
          >
            {payloadOpen ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
            原始 Payload
          </button>
          {payloadOpen ? (
            <pre className="mt-1.5 max-h-64 overflow-auto rounded-md border border-border-subtle bg-bg-page px-3 py-2 font-mono text-micro text-text-secondary">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}

      {/* 在源头打开 */}
      {externalUrlFromPayload(event) ? (
        <a
          href={externalUrlFromPayload(event) ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-accent-primary-dark transition hover:bg-bg-warm"
        >
          <ExternalLink className="size-3.5" />
          在源头打开
        </a>
      ) : null}
    </div>
  )
}

const SOURCE_LABEL: Record<string, string> = {
  github: 'GitHub',
  claude_code: 'Claude Code',
  cursor: 'Cursor',
  vscode: 'VS Code',
  local_file: '本地文档',
  manual: '手动录入',
}

const EVENT_TYPE_LABEL: Record<string, string> = {
  ai_conversation_turn: 'AI 对话',
  tool_call: '工具调用',
  code_change: '代码修改',
  pr_event: 'PR 事件',
  issue_event: 'Issue 事件',
  commit: 'Commit',
  local_document: '本地文档',
  manual_note: '手动笔记',
}

interface RedactionBadgeProps {
  state: Event['redaction_state']
}

function RedactionBadge({ state }: RedactionBadgeProps) {
  const map: Record<Event['redaction_state'], { label: string; tone: string }> = {
    raw: { label: '原始', tone: 'bg-bg-warm text-text-secondary' },
    screened: { label: '已扫描', tone: 'bg-info-bg text-info' },
    confirmed: { label: '已确认', tone: 'bg-success-bg text-success-dark' },
    exported: { label: '已导出', tone: 'bg-accent-primary-light text-accent-primary-dark' },
  }
  const { label, tone } = map[state]
  return (
    <span className={cn('rounded-full px-2 py-0.5 font-ui text-micro', tone)}>
      {label}
    </span>
  )
}

function externalUrlFromPayload(event: Event): string | null {
  // PR / Issue / Commit: payload.html_url / url
  const p = event.payload as Record<string, unknown> | undefined
  if (!p) return null
  for (const key of ['html_url', 'url', 'external_url']) {
    const v = p[key]
    if (typeof v === 'string' && v.startsWith('http')) return v
  }
  return null
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function DrawerLoading() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
      <Loader2 className="size-5 animate-spin" />
      <p className="font-ui text-caption">加载事件中…</p>
    </div>
  )
}

function DrawerError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-muted">
      <AlertCircle className="size-5 text-danger" />
      <p className="font-ui text-body-sm">事件加载失败</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md border border-border-subtle bg-bg-card px-3 py-1.5 font-ui text-caption text-accent-primary-dark transition hover:bg-bg-warm"
      >
        重试
      </button>
    </div>
  )
}
