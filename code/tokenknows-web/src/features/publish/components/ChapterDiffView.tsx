/**
 * ChapterDiffView · T12/P3 章节级 diff
 *
 * 用 `diff` 包 (jsdiff) 做行级 diff. 输入: 章节当前 content + 上一版 previous_content.
 * 渲染: 三色 (新增绿 / 删除红 / 上下文中性).
 *
 * MVP 选择 diffLines (行级) 而非 diffWords/diffChars: 章节内容 ~200-500 字,
 * 行级粒度对人阅读最友好, 性能也最低耗.
 */

import { useState } from 'react'
import { diffLines, type Change } from 'diff'
import { ChevronDown, ChevronRight, GitCompare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Chapter } from '@/types/api'

interface ChapterDiffViewProps {
  chapter: Chapter
  /** 默认展开第 1 个有 diff 的章节 (PublishReceiptPage 控制). */
  defaultExpanded?: boolean
}

// React 19 编译器会自动 memo, 函数内直接计算
function computeDiff(prev: string | undefined, curr: string): Change[] {
  if (!prev) return []
  return diffLines(prev, curr, { ignoreWhitespace: false })
}

function computeStats(changes: Change[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const c of changes) {
    const lines = c.value.split('\n').filter(Boolean).length
    if (c.added) added += lines
    if (c.removed) removed += lines
  }
  return { added, removed }
}

export function ChapterDiffView({ chapter, defaultExpanded }: ChapterDiffViewProps) {
  const lastRegen = chapter.regeneration_history.at(-1)
  const hasDiff = Boolean(lastRegen?.previous_content)
  const [expanded, setExpanded] = useState(Boolean(defaultExpanded && hasDiff))

  const changes = computeDiff(lastRegen?.previous_content, chapter.content)
  const stats = computeStats(changes)

  if (!hasDiff) {
    return (
      <article className="rounded-md border border-border-subtle bg-bg-card p-3">
        <header className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="font-content text-body-sm text-text-primary">
              §{chapter.order_index + 1} {chapter.title}
            </p>
            <p className="font-ui text-micro text-text-subtle">
              未经重生成, 无 diff 历史
            </p>
          </div>
        </header>
      </article>
    )
  }

  return (
    <article className="rounded-md border border-border-subtle bg-bg-card">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-bg-warm/50"
      >
        <div className="flex min-w-0 items-center gap-2">
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0 text-text-muted" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-text-muted" />
          )}
          <GitCompare className="size-3.5 shrink-0 text-info" />
          <div className="min-w-0">
            <p className="font-content text-body-sm text-text-primary">
              §{chapter.order_index + 1} {chapter.title}
            </p>
            <p className="font-ui text-micro text-text-subtle">
              指令: {lastRegen?.instruction}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-micro">
          <span className="rounded-full bg-success-bg px-1.5 py-0.5 text-success-dark">
            +{stats.added}
          </span>
          <span className="rounded-full bg-danger-bg px-1.5 py-0.5 text-danger">
            -{stats.removed}
          </span>
        </div>
      </button>
      {expanded ? (
        <div className="border-t border-border-subtle">
          <pre className="overflow-auto px-3 py-2 font-mono text-caption leading-relaxed">
            {changes.map((c, i) => (
              <DiffChunk key={i} change={c} />
            ))}
          </pre>
          <footer className="border-t border-border-subtle px-3 py-2 font-ui text-micro text-text-muted">
            重生成于{' '}
            <code className="font-mono">
              {lastRegen ? formatDateTime(lastRegen.at) : '?'}
            </code>{' '}
            · 模型 <code className="font-mono">{lastRegen?.model}</code>
          </footer>
        </div>
      ) : null}
    </article>
  )
}

interface DiffChunkProps {
  change: Change
}

function DiffChunk({ change }: DiffChunkProps) {
  // 单 chunk 可能多行, 每行单独着色 + 行首加 +/- 标记
  const lines = change.value.split('\n')
  // 末尾空字符串是 trailing newline 副产物, 去掉
  if (lines[lines.length - 1] === '') lines.pop()

  const tone = change.added
    ? 'bg-success-bg/40 text-success-dark'
    : change.removed
      ? 'bg-danger-bg/40 text-danger'
      : 'text-text-secondary'
  const sign = change.added ? '+' : change.removed ? '-' : ' '

  return (
    <>
      {lines.map((line, i) => (
        <span key={i} className={cn('block whitespace-pre-wrap px-1', tone)}>
          <span className="mr-2 select-none opacity-50">{sign}</span>
          {line || ' '}
        </span>
      ))}
    </>
  )
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
