/**
 * DocumentCard · 单个文档卡 (T05 列表)
 *
 * 决策 (TaskTechDesign T05):
 *   - 状态徽标严格按 token: draft=warning / in_review=info /
 *     approved=success / published=accent-primary
 *   - "复制"是克隆 asset (新草稿), 不是复制链接
 *   - generating 显示 Progress 卡而非常规
 */

import { useNavigate } from 'react-router-dom'
import { MoreHorizontal, Copy, Download, Trash2, Loader2 } from 'lucide-react'
import { formatRelative } from '@/lib/format'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import type { Asset, AssetStatus, AssetType } from '@/types/api'

interface DocumentCardProps {
  asset: Asset
  projectId: string
  onClone: (assetId: string) => void
  onDelete: (assetId: string, title: string) => void
}

const TYPE_LABEL: Record<AssetType, string> = {
  weekly_report: '周报',
  tech_design: '技术方案',
  adr: 'ADR',
  incident: '复盘',
  // v0.2 补全 (此前缺)
  book: '书籍',
  agent_skill: '专家技能',
  // v1.2 新增
  knowledge_graph: '知识图谱',
}

const STATUS_META: Record<
  AssetStatus,
  { label: string; bg: string; text: string; border: string }
> = {
  generating: {
    label: '生成中',
    bg: 'bg-bg-warm',
    text: 'text-text-muted',
    border: 'border-border-medium',
  },
  draft: {
    label: '草稿',
    bg: 'bg-warning-bg',
    text: 'text-warning',
    border: 'border-warning-border',
  },
  in_review: {
    label: '审批中',
    bg: 'bg-info-bg',
    text: 'text-info',
    border: 'border-info',
  },
  approved: {
    label: '已通过',
    bg: 'bg-success-bg',
    text: 'text-success-dark',
    border: 'border-success-border',
  },
  published: {
    label: '已发布',
    bg: 'bg-accent-primary-light',
    text: 'text-accent-primary-dark',
    border: 'border-accent-primary-border',
  },
  archived: {
    label: '已归档',
    bg: 'bg-bg-warm',
    text: 'text-text-subtle',
    border: 'border-border-subtle',
  },
}

export function DocumentCard({ asset, projectId, onClone, onDelete }: DocumentCardProps) {
  const navigate = useNavigate()
  const statusMeta = STATUS_META[asset.status]
  const isGenerating = asset.status === 'generating'

  const handleOpen = () => {
    if (isGenerating) return
    navigate(`/projects/${projectId}/documents/${asset.id}`)
  }

  return (
    <article
      className={cn(
        'group relative flex flex-col gap-3 rounded-lg border bg-bg-card p-4 transition',
        isGenerating
          ? 'border-border-subtle'
          : 'border-border-subtle hover:border-border-medium hover:shadow-elev-1 cursor-pointer',
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="rounded bg-bg-warm px-1.5 py-0.5 font-ui text-micro font-medium text-text-secondary">
            {TYPE_LABEL[asset.type]}
          </span>
          <span
            className={cn(
              'flex items-center gap-1 rounded border px-1.5 py-0.5 font-ui text-micro font-medium',
              statusMeta.bg,
              statusMeta.text,
              statusMeta.border,
            )}
          >
            {isGenerating ? <Loader2 className="size-2.5 animate-spin" /> : null}
            {statusMeta.label}
          </span>
        </div>
        {!isGenerating ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                onClick={(e) => e.stopPropagation()}
                className="rounded p-1 text-text-muted opacity-0 transition group-hover:opacity-100 hover:bg-bg-warm focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                aria-label="更多操作"
              >
                <MoreHorizontal className="size-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              onClick={(e) => e.stopPropagation()}
              className="w-40"
            >
              <DropdownMenuItem
                onSelect={() => onClone(asset.id)}
                className="font-ui text-body-sm"
              >
                <Copy className="size-3.5" />
                克隆
              </DropdownMenuItem>
              <DropdownMenuItem className="font-ui text-body-sm" disabled>
                <Download className="size-3.5" />
                导出 (T11)
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => onDelete(asset.id, asset.title)}
                className="font-ui text-body-sm text-danger focus:bg-danger-bg focus:text-danger"
              >
                <Trash2 className="size-3.5" />
                删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </header>

      <button
        type="button"
        onClick={handleOpen}
        disabled={isGenerating}
        className="flex flex-1 flex-col items-start gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary disabled:cursor-default"
      >
        <h3 className="line-clamp-2 font-content text-h3 text-text-primary">
          {asset.title}
        </h3>
        {isGenerating ? (
          <div className="w-full space-y-2 pt-1">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <p className="font-ui text-caption text-text-subtle">
              生成中 · 预计 5 秒... 完成后自动刷新
            </p>
          </div>
        ) : asset.metrics ? (
          <Metrics
            coverage={asset.metrics.coverage}
            citation={asset.metrics.citation_density}
            slop={asset.metrics.slop_score}
            similarity={asset.metrics.similarity}
          />
        ) : null}
      </button>

      <footer className="flex items-center justify-between font-ui text-caption text-text-subtle">
        <span>v{asset.current_version}</span>
        <time dateTime={asset.updated_at}>{formatRelative(asset.updated_at)}</time>
      </footer>
    </article>
  )
}

interface MetricsProps {
  coverage: number
  citation: number
  slop: number
  similarity: number
}

function Metrics({ coverage, citation, slop, similarity }: MetricsProps) {
  return (
    <ul className="flex w-full items-center gap-3 pt-1 font-ui text-caption text-text-muted">
      <li>
        覆盖 <strong className="font-mono text-text-secondary tabular-nums">{Math.round(coverage * 100)}%</strong>
      </li>
      <li>
        引用 <strong className="font-mono text-text-secondary tabular-nums">{Math.round(citation * 100)}%</strong>
      </li>
      <li>
        空话 <strong
          className={cn(
            'font-mono tabular-nums',
            slop > 0.2 ? 'text-warning' : 'text-text-secondary',
          )}
        >{Math.round(slop * 100)}%</strong>
      </li>
      <li
        title={
          similarity > 0.85
            ? '与项目内既往文档高度重合 — 可能在重复劳动'
            : '与项目内既往文档的最大相似度 (越低越独立)'
        }
      >
        相似 <strong
          className={cn(
            'font-mono tabular-nums',
            similarity > 0.85
              ? 'text-danger'
              : similarity > 0.6
                ? 'text-warning'
                : 'text-text-secondary',
          )}
        >{Math.round(similarity * 100)}%</strong>
      </li>
    </ul>
  )
}

