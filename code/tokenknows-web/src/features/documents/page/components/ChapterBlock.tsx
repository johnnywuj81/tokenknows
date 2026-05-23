/**
 * ChapterBlock · 单章节卡
 *
 * Phase 1: markdown-it 静态渲染
 * Phase 2: TipTap editor + useChapterAutosave (debounce 2s)
 * Phase 3: InlineEvidence [N] 角标 + 重生成 disable
 * P2: EvidenceBadge 自定义 Node 接入, [N] 在编辑器内可被识别为 atom 单元,
 *     编辑后保存仍可往返
 * A3 (v0.2): content > 20KB 默认走 LazyChapterEditor 预览态, 避免大文本卡顿.
 */

import { useMemo } from 'react'
import MarkdownIt from 'markdown-it'
import { Loader2, CheckCircle2, AlertCircle, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Chapter } from '@/types/api'
import { ChapterFooter } from './ChapterFooter'
import { useChapterAutosave, type AutosaveState } from '../../hooks/useChapterAutosave'
import { LazyChapterEditor } from './LazyChapterEditor'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// content 可能是 markdown (后端生成) 或 HTML (前端编辑过). 自动识别.
function toEditorHTML(content: string): string {
  const trimmed = content.trim()
  if (trimmed.startsWith('<')) return content
  return md.render(content)
}
// 把后端 markdown 渲染后产生的纯文本 `[N]` 转成 evidence-badge span
// (有 data-evidence-id 占位 ev-<chapter>-N + data-index=N), 让 EvidenceBadge
// 的 parseHTML 接管成 Node. 编辑后输出 HTML 也是相同 span 结构, 因此可逆.
function annotateEvidence(html: string, chapterId: string): string {
  return html.replace(
    /\[(\d+)\]/g,
    (_match, idx) =>
      `<span class="evidence-badge" data-evidence-id="ev-${chapterId}-${idx}" data-index="${idx}" contenteditable="false">${idx}</span>`,
  )
}


interface ChapterBlockProps {
  chapter: Chapter
  /** 重生成中? 重生成与编辑互斥 (任务包 T06 关键决策). */
  regenerating?: boolean
  /** T09 审批视角下编辑器只读 (无 autosave). */
  readOnly?: boolean
  onRegenerate?: (chapterId: string) => void
  onViewEvidence?: (chapterId: string, evidenceId?: string) => void
}

export function ChapterBlock({
  chapter,
  regenerating,
  readOnly,
  onRegenerate,
  onViewEvidence,
}: ChapterBlockProps) {
  const autosave = useChapterAutosave(chapter)
  const { state, savedContent, handleEdit, error } = autosave
  const initialHTML = useMemo(
    () => annotateEvidence(toEditorHTML(savedContent), chapter.id),
    [savedContent, chapter.id],
  )
  const editable = !readOnly && !regenerating

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

      {/* T128 · 章节被 reviewer 退回时显示退回理由 (从 regeneration_history 抽 [REJECT] 那条) */}
      <RejectReasonBanner chapter={chapter} />

      {/* A3 · 长文档懒挂载: content > 20KB 默认预览, 点击展开才挂 TipTap */}
      <LazyChapterEditor
        chapterId={chapter.id}
        initialHTML={initialHTML}
        rawLength={savedContent.length}
        editable={editable}
        onEdit={handleEdit}
        onViewEvidence={onViewEvidence}
        autosaveState={state}
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


// ── T128 · 退回理由 banner ──────────────────────────────────────


/**
 * 从 regeneration_history 找最新一条 `[REJECT] <reason>` 记录, 抽出理由 + 时间.
 * 没有 reject 记录或 chapter 状态不是 rejected 时返 null.
 */
function _latestRejection(chapter: Chapter): { reason: string; at: string } | null {
  if (chapter.approval_state !== 'rejected') return null
  const history = chapter.regeneration_history ?? []
  // 倒序找首个 [REJECT] 开头
  for (let i = history.length - 1; i >= 0; i--) {
    const h = history[i]
    if (typeof h.instruction === 'string' && h.instruction.startsWith('[REJECT] ')) {
      return { reason: h.instruction.slice('[REJECT] '.length), at: h.at }
    }
  }
  // 状态是 rejected 但没找到对应记录 (旧数据 / 异常), 仍返一个空 placeholder
  // 让作者知道这章被退回了
  return { reason: '(未填理由)', at: '' }
}


function _fmtAt(at: string): string {
  if (!at) return ''
  try {
    const d = new Date(at)
    if (Number.isNaN(d.getTime())) return at
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return at
  }
}


function RejectReasonBanner({ chapter }: { chapter: Chapter }) {
  const reject = _latestRejection(chapter)
  if (!reject) return null
  return (
    <div
      role="alert"
      data-testid={`chapter-reject-banner-${chapter.id}`}
      className="flex items-start gap-2 rounded-md border border-danger-border bg-danger-bg/40 px-3 py-2"
    >
      <XCircle className="size-4 shrink-0 mt-0.5 text-danger" />
      <div className="flex-1 min-w-0">
        <p className="font-ui text-body-sm font-medium text-danger-dark">
          审批人退回了本章
          {reject.at ? (
            <span className="ml-2 font-normal text-caption text-text-muted">
              · {_fmtAt(reject.at)}
            </span>
          ) : null}
        </p>
        <p className="mt-1 font-ui text-caption text-text-secondary whitespace-pre-wrap break-words">
          {reject.reason}
        </p>
      </div>
    </div>
  )
}
