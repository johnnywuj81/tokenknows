/**
 * ChapterBlock · 单章节卡 (Phase 2: TipTap editor + 自动保存)
 *
 * Phase 1: markdown-it 静态渲染
 * Phase 2 (本提交): TipTap editor + useChapterAutosave (debounce 2s)
 * Phase 3 (后续): InlineEvidence [N] 角标 + 重生成 disable
 */

import { useEffect, useMemo } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import MarkdownIt from 'markdown-it'
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Chapter } from '@/types/api'
import { ChapterFooter } from './ChapterFooter'
import { useChapterAutosave, type AutosaveState } from '../../hooks/useChapterAutosave'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// content 可能是 markdown (后端生成) 或 HTML (前端编辑过). 自动识别.
function toEditorHTML(content: string): string {
  const trimmed = content.trim()
  if (trimmed.startsWith('<')) return content
  return md.render(content)
}
// 把 [N] 形式标注转成可点击 evidence-badge.
// contenteditable=false 让 TipTap 不把它当编辑内容; click 委托捕获.
function annotateEvidence(html: string, chapterId: string): string {
  return html.replace(
    /\[(\d+)\]/g,
    (_match, idx) =>
      `<span class="evidence-badge" data-evidence-id="ev-${chapterId}-${idx}" contenteditable="false">${idx}</span>`,
  )
}


interface ChapterBlockProps {
  chapter: Chapter
  /** 重生成中? 重生成与编辑互斥 (任务包 T06 关键决策). */
  regenerating?: boolean
  onRegenerate?: (chapterId: string) => void
  onViewEvidence?: (chapterId: string, evidenceId?: string) => void
}

export function ChapterBlock({
  chapter,
  regenerating,
  onRegenerate,
  onViewEvidence,
}: ChapterBlockProps) {
  const { state, savedContent, handleEdit, error } = useChapterAutosave(chapter)
  const initialHTML = useMemo(
    () => annotateEvidence(toEditorHTML(savedContent), chapter.id),
    [savedContent, chapter.id],
  )

  const editor = useEditor(
    {
      extensions: [
        StarterKit,
        Placeholder.configure({
          placeholder: '开始编辑章节内容…',
        }),
        Link.configure({ openOnClick: false, autolink: true }),
      ],
      content: initialHTML,
      editable: !regenerating,
      onUpdate: ({ editor: e }) => {
        if (regenerating) return
        handleEdit(e.getHTML())
      },
    },
    [chapter.id],
  )

  // 章节外部刷新 (e.g. 重生成完成) → setContent 同步, 不触发 onUpdate
  useEffect(() => {
    if (!editor) return
    const next = annotateEvidence(toEditorHTML(savedContent), chapter.id)
    if (editor.getHTML() !== next) {
      editor.commands.setContent(next, { emitUpdate: false })
    }
  }, [savedContent, editor, chapter.id])

  // editable 跟随 regenerating
  useEffect(() => {
    editor?.setEditable(!regenerating)
  }, [editor, regenerating])

  return (
    <article
      id={`chapter-anchor-${chapter.id}`}
      className={cn(
        'scroll-mt-6 space-y-3 rounded-lg border bg-bg-card px-5 py-4 transition',
        regenerating ? 'border-info-border bg-info-bg/30' : 'border-border-subtle',
      )}
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-border-subtle pb-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-caption text-text-subtle">
            §{chapter.order_index + 1}
          </span>
          <h2 className="font-content text-h3 text-text-primary">{chapter.title}</h2>
        </div>
        <div className="flex items-center gap-2">
          <SaveBadge state={state} error={error} />
          {chapter.generated_by ? (
            <span
              className="font-ui text-micro text-text-subtle"
              title={`provider=${chapter.generated_by.provider} model=${chapter.generated_by.model}`}
            >
              {chapter.generated_by.provider} · {chapter.generated_by.model.split('-')[0]}
            </span>
          ) : null}
        </div>
      </header>

      {regenerating ? (
        <div className="flex items-center gap-2 rounded-md border border-info-border bg-info-bg px-3 py-2 text-info">
          <Loader2 className="size-3.5 animate-spin" />
          <span className="font-ui text-caption">本章重生成中, 编辑已禁用</span>
        </div>
      ) : null}

      <EditorContent
        editor={editor}
        className="tiptap-prose font-content text-body-lg text-text-secondary leading-relaxed focus-visible:outline-none"
        onClickCapture={(e) => {
          const target = (e.target as HTMLElement).closest('[data-evidence-id]')
          if (target) {
            e.preventDefault()
            e.stopPropagation()
            const evId = target.getAttribute('data-evidence-id')
            if (evId) onViewEvidence?.(chapter.id, evId)
          }
        }}
      />

      <ChapterFooter
        chapter={chapter}
        onRegenerate={onRegenerate}
        onViewEvidence={onViewEvidence}
      />
    </article>
  )
}

interface SaveBadgeProps {
  state: AutosaveState
  error: string | null
}

function SaveBadge({ state, error }: SaveBadgeProps) {
  if (state === 'idle') return null
  if (state === 'editing') {
    return (
      <span className="font-ui text-micro text-text-subtle">编辑中…</span>
    )
  }
  if (state === 'saving') {
    return (
      <span className="flex items-center gap-1 font-ui text-micro text-text-muted">
        <Loader2 className="size-2.5 animate-spin" />
        保存中
      </span>
    )
  }
  if (state === 'saved') {
    return (
      <span className="flex items-center gap-1 font-ui text-micro text-success-dark">
        <CheckCircle2 className="size-2.5" />
        已保存
      </span>
    )
  }
  return (
    <span
      className="flex items-center gap-1 font-ui text-micro text-danger"
      title={error ?? '保存失败'}
    >
      <AlertCircle className="size-2.5" />
      已存本地 (重试中)
    </span>
  )
}
