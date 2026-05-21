/**
 * EvidenceSourceCard · T07 单条证据详情卡
 *
 * 渲染 Evidence + event_preview 的完整信息:
 *   - 标题 / 来源类型 icon + source_ref
 *   - 作者 + 发生时间
 *   - 原文摘录 (content_excerpt)
 *   - trust_score + citation_strength 指标
 *   - "在源头打开" 外链
 *
 * 设计依据: T07 任务包 §3 (证据链抽屉规格)
 */

import {
  GitPullRequest,
  MessageSquare,
  FileText,
  User as UserIcon,
  Terminal,
  ExternalLink,
  Quote,
  Calendar,
  CircleAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import type { Evidence } from '@/types/api'
import { cn } from '@/lib/utils'

interface EvidenceSourceCardProps {
  evidence: Evidence
}

const SOURCE_LABEL: Record<string, string> = {
  github: 'GitHub',
  claude_code: 'Claude Code',
  cursor: 'Cursor',
  vscode: 'VS Code',
  local_file: '本地文档',
  manual: '手动录入',
}

function renderSourceIcon(sourceType: string): ReactNode {
  const className = 'size-3.5'
  switch (sourceType) {
    case 'github':
      return <GitPullRequest className={className} />
    case 'claude_code':
    case 'cursor':
    case 'vscode':
      return <Terminal className={className} />
    case 'local_file':
      return <FileText className={className} />
    case 'manual':
      return <UserIcon className={className} />
    default:
      return <MessageSquare className={className} />
  }
}

function formatOccurredAt(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
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

export function EvidenceSourceCard({ evidence }: EvidenceSourceCardProps) {
  const preview = evidence.event_preview
  const sourceLabel = SOURCE_LABEL[preview.source_type] ?? preview.source_type

  return (
    <div className="space-y-4 rounded-lg border border-border-subtle bg-bg-card p-4">
      {/* 标题 + 来源 */}
      <header className="space-y-2">
        <div className="flex items-center gap-1.5 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          {renderSourceIcon(preview.source_type)}
          <span>{sourceLabel}</span>
          <span className="text-text-subtle">·</span>
          <span className="font-mono text-text-subtle">{preview.source_ref}</span>
        </div>
        <h3 className="font-content text-h3 text-text-primary leading-snug">
          {preview.title ?? '(无标题)'}
        </h3>
      </header>

      {/* 作者 + 时间 */}
      <dl className="grid grid-cols-2 gap-3 font-ui text-caption">
        <div>
          <dt className="text-text-subtle uppercase tracking-wider text-micro">作者</dt>
          <dd className="mt-0.5 flex items-center gap-1 text-text-secondary">
            <UserIcon className="size-3 text-text-subtle" />
            <span>{preview.author_name ?? '未知'}</span>
          </dd>
          {preview.author_email ? (
            <dd className="mt-0.5 font-mono text-micro text-text-subtle">
              {preview.author_email}
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="text-text-subtle uppercase tracking-wider text-micro">发生时间</dt>
          <dd className="mt-0.5 flex items-center gap-1 text-text-secondary">
            <Calendar className="size-3 text-text-subtle" />
            <span>{formatOccurredAt(preview.occurred_at)}</span>
          </dd>
        </div>
      </dl>

      {/* 原文摘录 */}
      <div>
        <p className="font-ui text-micro uppercase tracking-wider text-text-subtle">
          原文摘录
        </p>
        <blockquote className="mt-1.5 flex gap-2 rounded-md border-l-2 border-accent-primary bg-bg-warm/40 px-3 py-2">
          <Quote className="mt-0.5 size-3 shrink-0 text-text-subtle" />
          <p className="font-content text-body-sm text-text-secondary leading-relaxed">
            {preview.content_excerpt}
          </p>
        </blockquote>
      </div>

      {/* 指标 */}
      <div className="flex flex-wrap items-center gap-2">
        {typeof evidence.trust_score === 'number' ? (
          <ScoreBadge label="trust" value={evidence.trust_score} />
        ) : null}
        {typeof evidence.citation_strength === 'number' ? (
          <ScoreBadge label="citation" value={evidence.citation_strength} />
        ) : null}
        {evidence.manually_added ? (
          <span className="rounded-full bg-info-bg px-2 py-0.5 font-ui text-micro text-info">
            手动添加
          </span>
        ) : null}
        {evidence.stale ? (
          <span className="flex items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 font-ui text-micro text-warning">
            <CircleAlert className="size-2.5" />
            已过期
          </span>
        ) : null}
      </div>

      {/* 在源头打开 */}
      {preview.external_url ? (
        <a
          href={preview.external_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-accent-primary-dark transition hover:bg-bg-warm"
        >
          <ExternalLink className="size-3.5" />
          在源头打开
        </a>
      ) : (
        <button
          type="button"
          disabled
          className="flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-bg-page px-3 py-2 font-ui text-body-sm text-text-subtle"
        >
          <ExternalLink className="size-3.5" />
          无外链
        </button>
      )}
    </div>
  )
}

interface ScoreBadgeProps {
  label: string
  value: number
}

function ScoreBadge({ label, value }: ScoreBadgeProps) {
  const pct = Math.round(value * 100)
  const tone =
    value >= 0.8
      ? 'bg-success-bg text-success-dark'
      : value >= 0.5
        ? 'bg-info-bg text-info-dark'
        : 'bg-warning-bg text-warning-dark'

  return (
    <span
      className={cn(
        'flex items-center gap-1 rounded-full px-2 py-0.5 font-ui text-micro',
        tone,
      )}
      title={`${label}=${value.toFixed(3)}`}
    >
      <span className="uppercase tracking-wider">{label}</span>
      <span className="font-mono font-semibold">{pct}</span>
    </span>
  )
}
