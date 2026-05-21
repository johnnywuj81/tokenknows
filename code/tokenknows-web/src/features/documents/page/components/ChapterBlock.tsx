/**
 * ChapterBlock · 单章节卡 (Phase 1: markdown-it 渲染)
 *
 * Phase 1: 静态 markdown 渲染 (read-only)
 * Phase 2: 换 TipTap editor (可编辑 + 自动保存)
 * Phase 3: ChapterFooter + InlineEvidence 接入证据/重生成
 */

import { useMemo } from 'react'
import MarkdownIt from 'markdown-it'
import type { Chapter } from '@/types/api'
import { ChapterFooter } from './ChapterFooter'

// 单例 markdown-it - 配置 html=false 安全防 XSS
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

interface ChapterBlockProps {
  chapter: Chapter
  onRegenerate?: (chapterId: string) => void
  onViewEvidence?: (chapterId: string) => void
}

export function ChapterBlock({ chapter, onRegenerate, onViewEvidence }: ChapterBlockProps) {
  const html = useMemo(() => md.render(chapter.content || ''), [chapter.content])

  return (
    <article
      id={`chapter-anchor-${chapter.id}`}
      className="scroll-mt-6 space-y-3 rounded-lg border border-border-subtle bg-bg-card px-5 py-4"
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-border-subtle pb-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-caption text-text-subtle">
            §{chapter.order_index + 1}
          </span>
          <h2 className="font-content text-h3 text-text-primary">
            {chapter.title}
          </h2>
        </div>
        {chapter.generated_by ? (
          <span
            className="font-ui text-micro text-text-subtle"
            title={`provider=${chapter.generated_by.provider} latency=${chapter.generated_by.latency_ms}ms`}
          >
            {chapter.generated_by.provider} · {chapter.generated_by.model.split('-')[0]}
          </span>
        ) : null}
      </header>

      <div
        className="markdown-body font-content text-body-lg text-text-secondary leading-relaxed"
        // markdown-it 已 escape, html=false 安全
        dangerouslySetInnerHTML={{ __html: html }}
      />

      <ChapterFooter
        chapter={chapter}
        onRegenerate={onRegenerate}
        onViewEvidence={onViewEvidence}
      />
    </article>
  )
}
