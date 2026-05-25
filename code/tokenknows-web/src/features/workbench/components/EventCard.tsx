/**
 * EventCard · 单条研发事件
 *
 * 决策依据 (任务包 T03 §8):
 *   左侧色条按 event_type 分色:
 *     commit(success) / pr_event,issue_event(accent-primary) /
 *     ai_conversation_turn(info) / 其他(text-muted)
 *   icon 按 source_type 区分。
 */

import { Code2, FileCode, GitCommit, GitPullRequest, MessageSquare, Upload, Wrench, FileText } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { GithubIcon } from '@/components/icons/GithubIcon'
import type { Event, EventType, EventSourceType } from '@/types/api'
import { cn } from '@/lib/utils'

interface EventCardProps {
  event: Event
  onClick?: () => void
}

const ICON_CLASS = 'size-4 mt-0.5 shrink-0 text-text-secondary'

// T141: source 类型 chip 标签 (跟 DatasourcesCard / EventDrawer 对齐).
// 之前 EventCard 只用 icon 区分 source, 用户分不清这条是 Claude Code 还是
// Claude Cowork / Cursor / etc., 反复抱怨 "code 事件流没看到" → 加显式 chip.
const SOURCE_LABEL: Record<EventSourceType, string> = {
  claude_code: 'Claude Code',
  claude_cowork: 'Claude Cowork',
  cursor: 'Cursor',
  vscode: 'VS Code',
  github: 'GitHub',
  local_file: '本地文档',
  manual: '手动',
}

export function EventCard({ event, onClick }: EventCardProps) {
  const sideClass = sideColor(event.event_type)
  const iconNode = renderIcon(event.source_type, event.event_type)
  const initials = (event.author?.name ?? '?').slice(0, 1).toUpperCase()
  const time = new Date(event.occurred_at).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <article
      className={cn(
        'group relative overflow-hidden rounded-md border border-border-subtle bg-bg-card transition hover:border-border-medium hover:bg-bg-warm/50',
        'animate-in fade-in duration-150',
      )}
    >
      <span className={cn('absolute left-0 top-0 h-full w-1', sideClass)} aria-hidden="true" />
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-start gap-3 px-3 py-2.5 pl-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
      >
        {iconNode}
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="line-clamp-2 font-ui text-body-sm text-text-primary">
            {event.title ?? eventTypeLabel(event.event_type)}
          </h3>
          <div className="flex items-center gap-2 text-text-subtle">
            <span
              className="rounded-sm bg-bg-warm px-1.5 py-0 font-ui text-micro text-text-secondary"
              title={`source_type: ${event.source_type}`}
            >
              {SOURCE_LABEL[event.source_type] ?? event.source_type}
            </span>
            {event.author ? (
              <span className="flex items-center gap-1.5">
                <Avatar className="size-4">
                  <AvatarFallback className="bg-accent-primary-light text-accent-primary-dark text-micro">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <span className="font-ui text-caption">{event.author.name}</span>
              </span>
            ) : null}
            <span className="font-ui text-caption">·</span>
            <span className="truncate font-mono text-caption text-text-muted" title={event.source_ref}>
              {event.source_ref}
            </span>
            <span className="font-ui text-caption">·</span>
            <time className="font-mono text-caption">{time}</time>
          </div>
        </div>
        {event.trust_score ? (
          <span
            className="font-ui text-micro text-text-subtle"
            title={`trust_score: ${event.trust_score.toFixed(2)}`}
          >
            {(event.trust_score * 100).toFixed(0)}
          </span>
        ) : null}
      </button>
    </article>
  )
}

function sideColor(type: EventType): string {
  switch (type) {
    case 'commit':
      return 'bg-success'
    case 'pr_event':
    case 'issue_event':
      return 'bg-accent-primary'
    case 'ai_conversation_turn':
      return 'bg-info'
    default:
      return 'bg-border-medium'
  }
}

function renderIcon(source: EventSourceType, eventType: EventType): React.ReactNode {
  if (eventType === 'commit') return <GitCommit className={ICON_CLASS} />
  if (eventType === 'pr_event') return <GitPullRequest className={ICON_CLASS} />
  if (eventType === 'issue_event') return <FileText className={ICON_CLASS} />
  if (eventType === 'tool_call') return <Wrench className={ICON_CLASS} />
  if (source === 'github') return <GithubIcon className={ICON_CLASS} />
  if (source === 'claude_code') return <MessageSquare className={ICON_CLASS} />
  if (source === 'cursor') return <Code2 className={ICON_CLASS} />
  if (source === 'vscode') return <FileCode className={ICON_CLASS} />
  if (source === 'local_file') return <Upload className={ICON_CLASS} />
  return <MessageSquare className={ICON_CLASS} />
}

function eventTypeLabel(type: EventType): string {
  switch (type) {
    case 'ai_conversation_turn': return 'AI 对话'
    case 'tool_call': return '工具调用'
    case 'code_change': return '代码修改'
    case 'pr_event': return 'PR 事件'
    case 'issue_event': return 'Issue 事件'
    case 'commit': return 'Commit'
    case 'local_document': return '本地文档'
    case 'manual_note': return '手动笔记'
    default: return '事件'
  }
}
