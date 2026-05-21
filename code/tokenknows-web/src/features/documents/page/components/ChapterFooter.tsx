/**
 * ChapterFooter · 章节底部操作条
 *
 * 任务包 T06 §8 验收: "每章 footer 有: 重生成 → T08 / 查看证据 → T07 / 批注"
 */

import { RefreshCcw, BookText, MessageSquare } from 'lucide-react'
import type { Chapter } from '@/types/api'

interface ChapterFooterProps {
  chapter: Chapter
  onRegenerate?: (chapterId: string) => void
  onViewEvidence?: (chapterId: string) => void
}

export function ChapterFooter({ chapter, onRegenerate, onViewEvidence }: ChapterFooterProps) {
  return (
    <footer className="flex items-center justify-between gap-3 border-t border-border-subtle pt-2">
      <div className="flex items-center gap-2">
        <FooterButton
          icon={RefreshCcw}
          label="重生成"
          onClick={() => onRegenerate?.(chapter.id)}
          disabled={!onRegenerate}
        />
        <FooterButton
          icon={BookText}
          label="查看证据"
          onClick={() => onViewEvidence?.(chapter.id)}
          disabled={!onViewEvidence}
        />
        <FooterButton
          icon={MessageSquare}
          label="批注"
          disabled
          tooltip="T09 审批阶段实现"
        />
      </div>
      <span className="font-ui text-micro text-text-subtle">
        v{chapter.asset_version} · {chapter.approval_state}
      </span>
    </footer>
  )
}

interface FooterButtonProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  onClick?: () => void
  disabled?: boolean
  tooltip?: string
}

function FooterButton({ icon: Icon, label, onClick, disabled, tooltip }: FooterButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={tooltip}
      className="flex items-center gap-1 rounded-md px-2 py-1 font-ui text-caption text-text-muted transition hover:bg-bg-warm hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Icon className="size-3" />
      {label}
    </button>
  )
}
