/**
 * LazyChapterEditor · TipTap 编辑器懒挂载封装.
 *
 * A3 (v0.2 升级): content.length > LONG_THRESHOLD 时, 默认不挂载 TipTap,
 * 改用只读 markdown 预览 + "展开编辑" 按钮 (避免 100+ KB 单实例渲染卡顿).
 * 用户点击 "展开编辑" 才挂载真正 useEditor hook.
 *
 * 接口与原 ChapterBlock 内联编辑器一致, 通过 props 注入 autosave + 点击委托.
 */

import { useEffect, useMemo, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Link from '@tiptap/extension-link'
import { Edit3, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EvidenceBadge } from '../tiptap/EvidenceBadge'
import type { AutosaveState } from '../../hooks/useChapterAutosave'

/** 字符数阈值: 超过则默认走预览模式 (~ 5K 中文字 ≈ 7-10 段). */
export const LONG_CHAPTER_THRESHOLD = 20_000

interface LazyChapterEditorProps {
  chapterId: string
  /** 已注解好 [N] → evidence-badge span 的 HTML, 由父组件预处理. */
  initialHTML: string
  /** 用于计算长度判定的原始 markdown/HTML. */
  rawLength: number
  editable: boolean
  onEdit: (newHTML: string) => void
  onViewEvidence?: (chapterId: string, evidenceId?: string) => void
  /** 调试用: 传入 autosave state 仅给 prop drilling 一致, 编辑器本身不读. */
  autosaveState?: AutosaveState
}


export function LazyChapterEditor({
  chapterId,
  initialHTML,
  rawLength,
  editable,
  onEdit,
  onViewEvidence,
}: LazyChapterEditorProps) {
  // 长文档: 默认预览模式; 短文档: 直接进入编辑.
  // 一旦展开过, 不自动折回 (用户已读取 → 编辑器已挂载).
  const isLong = rawLength > LONG_CHAPTER_THRESHOLD
  const [expanded, setExpanded] = useState(!isLong)

  if (!expanded) {
    return (
      <LongChapterPreview
        chapterId={chapterId}
        initialHTML={initialHTML}
        rawLength={rawLength}
        onExpand={() => setExpanded(true)}
        onViewEvidence={onViewEvidence}
      />
    )
  }

  return (
    <MountedEditor
      chapterId={chapterId}
      initialHTML={initialHTML}
      editable={editable}
      onEdit={onEdit}
      onViewEvidence={onViewEvidence}
    />
  )
}


// ── 真正的 TipTap 编辑器 (与原 ChapterBlock 行为一致) ──────────────


interface MountedEditorProps {
  chapterId: string
  initialHTML: string
  editable: boolean
  onEdit: (newHTML: string) => void
  onViewEvidence?: (chapterId: string, evidenceId?: string) => void
}


function MountedEditor({
  chapterId,
  initialHTML,
  editable,
  onEdit,
  onViewEvidence,
}: MountedEditorProps) {
  const editor = useEditor(
    {
      extensions: [
        StarterKit,
        Placeholder.configure({
          placeholder: '开始编辑章节内容…',
        }),
        Link.configure({ openOnClick: false, autolink: true }),
        EvidenceBadge,
      ],
      content: initialHTML,
      editable,
      onUpdate: ({ editor: e }) => {
        if (!editable) return
        onEdit(e.getHTML())
      },
    },
    [chapterId],
  )

  // 章节外部刷新 (e.g. 重生成完成) → setContent 同步, 不触发 onUpdate
  useEffect(() => {
    if (!editor) return
    if (editor.getHTML() !== initialHTML) {
      editor.commands.setContent(initialHTML, { emitUpdate: false })
    }
  }, [initialHTML, editor])

  // editable 跟随 regenerating / readOnly
  useEffect(() => {
    editor?.setEditable(editable)
  }, [editor, editable])

  return (
    <EditorContent
      editor={editor}
      className="tiptap-prose font-content text-body-lg text-text-secondary leading-relaxed focus-visible:outline-none"
      onClickCapture={(e) => {
        const target = (e.target as HTMLElement).closest('[data-evidence-id]')
        if (target) {
          e.preventDefault()
          e.stopPropagation()
          const evId = target.getAttribute('data-evidence-id')
          if (evId) onViewEvidence?.(chapterId, evId)
        }
      }}
    />
  )
}


// ── 长文档预览态 (只读 markdown / HTML 静态渲染) ─────────────────────


interface LongChapterPreviewProps {
  chapterId: string
  initialHTML: string
  rawLength: number
  onExpand: () => void
  onViewEvidence?: (chapterId: string, evidenceId?: string) => void
}


function LongChapterPreview({
  chapterId,
  initialHTML,
  rawLength,
  onExpand,
  onViewEvidence,
}: LongChapterPreviewProps) {
  // 估算字符数 (约 / 2 ≈ 字数), 显示给用户
  const sizeHint = useMemo(() => {
    if (rawLength < 1000) return `${rawLength} 字符`
    if (rawLength < 10_000) return `${(rawLength / 1000).toFixed(1)}K 字符`
    return `${(rawLength / 1000).toFixed(0)}K 字符`
  }, [rawLength])

  return (
    <div className="space-y-3">
      <div
        className="flex items-start gap-2 rounded-md border border-info-border bg-info-bg/40 px-3 py-2 text-info"
        role="status"
      >
        <FileText className="size-4 shrink-0 mt-0.5" />
        <div className="flex-1 space-y-1">
          <p className="font-ui text-body-sm font-medium text-text-primary">
            长章节预览模式 · {sizeHint}
          </p>
          <p className="font-ui text-caption text-text-muted">
            为避免大文本编辑器卡顿, 默认显示只读渲染。点击下方按钮挂载富文本编辑器后可编辑。
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onExpand}
            className="mt-2 font-ui text-caption"
          >
            <Edit3 className="size-3.5" />
            展开编辑
          </Button>
        </div>
      </div>
      <div
        className="tiptap-prose font-content text-body-lg text-text-secondary leading-relaxed"
        dangerouslySetInnerHTML={{ __html: initialHTML }}
        onClickCapture={(e) => {
          // 仍支持 evidence badge 点击 → 打开抽屉
          const target = (e.target as HTMLElement).closest('[data-evidence-id]')
          if (target) {
            e.preventDefault()
            e.stopPropagation()
            const evId = target.getAttribute('data-evidence-id')
            if (evId) onViewEvidence?.(chapterId, evId)
          }
        }}
      />
    </div>
  )
}
