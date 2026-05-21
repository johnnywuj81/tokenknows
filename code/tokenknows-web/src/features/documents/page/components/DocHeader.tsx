/**
 * DocHeader · 文档页顶部
 *
 * 标题 + 类型徽标 + 版本 + 状态徽标 + 自评卡 + 提交审批 CTA
 * 设计依据 任务包 T06 §8: "顶部: 标题 · 类型徽标 · 版本 · 状态 · 自评卡"
 */

import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Asset, AssetStatus, AssetType } from '@/types/api'
import { SelfAssessCard } from './SelfAssessCard'

interface DocHeaderProps {
  asset: Asset
  saving?: boolean
  onSubmit?: () => void
  submitting?: boolean
  onPublish?: () => void
}

const TYPE_LABEL: Record<AssetType, string> = {
  weekly_report: '周报',
  tech_design: '技术方案',
  adr: 'ADR',
  incident: '问题复盘',
}

const STATUS_META: Record<
  AssetStatus,
  { label: string; bg: string; text: string }
> = {
  generating: { label: '生成中', bg: 'bg-bg-warm', text: 'text-text-muted' },
  draft: { label: '草稿', bg: 'bg-warning-bg', text: 'text-warning' },
  in_review: { label: '审批中', bg: 'bg-info-bg', text: 'text-info' },
  approved: { label: '已通过', bg: 'bg-success-bg', text: 'text-success-dark' },
  published: {
    label: '已发布',
    bg: 'bg-accent-primary-light',
    text: 'text-accent-primary-dark',
  },
  archived: { label: '已归档', bg: 'bg-bg-warm', text: 'text-text-subtle' },
}

export function DocHeader({
  asset,
  saving,
  onSubmit,
  submitting,
  onPublish,
}: DocHeaderProps) {
  const navigate = useNavigate()
  const statusMeta = STATUS_META[asset.status]
  const canSubmit = asset.status === 'draft'
  const canPublish = asset.status === 'approved' || asset.status === 'published'

  return (
    <header className="flex items-start justify-between gap-4 border-b border-border-subtle bg-bg-card px-6 py-3">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="-ml-1 rounded p-1 text-text-muted transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
            aria-label="返回"
          >
            <ArrowLeft className="size-3.5" />
          </button>
          <span className="rounded bg-bg-warm px-1.5 py-0.5 font-ui text-micro font-medium text-text-secondary">
            {TYPE_LABEL[asset.type]}
          </span>
          <span
            className={cn(
              'rounded px-1.5 py-0.5 font-ui text-micro font-medium',
              statusMeta.bg,
              statusMeta.text,
            )}
          >
            {statusMeta.label}
          </span>
          <span className="font-mono text-caption text-text-subtle">
            v{asset.current_version}
          </span>
          {saving ? (
            <span className="flex items-center gap-1 font-ui text-caption text-text-muted">
              <Loader2 className="size-3 animate-spin" />
              保存中
            </span>
          ) : null}
        </div>
        <h1 className="line-clamp-1 font-content text-h2 text-text-primary">
          {asset.title}
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <SelfAssessCard metrics={asset.metrics} loading={asset.status === 'generating'} />
        {canSubmit ? (
          <Button
            onClick={onSubmit}
            disabled={submitting}
            className="font-ui"
          >
            {submitting ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                提交中
              </>
            ) : (
              <>
                <Send className="size-3.5" />
                提交审批
              </>
            )}
          </Button>
        ) : null}
        {canPublish && onPublish ? (
          <Button
            onClick={onPublish}
            variant={asset.status === 'published' ? 'outline' : 'default'}
            className="font-ui"
          >
            <Upload className="size-3.5" />
            {asset.status === 'published' ? '再次发布' : '发布'}
          </Button>
        ) : null}
      </div>
    </header>
  )
}
