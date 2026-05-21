/**
 * T12 · PublishReceiptPage (发布回执)
 *
 * 展示:
 *   - 大对勾 + 版本号
 *   - 当前 record 的渠道链接 + 复制按钮
 *   - 同 asset 的所有发布历史 (按时间倒序)
 *
 * MVP 不做的 (留 TODO):
 *   - 版本 diff (T12 §8 要 diff 包) - 跳过
 *   - 撤回发布 - 跳过 (T13 凭证完成后回填)
 */

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  CheckCircle2,
  Copy,
  ExternalLink,
  Building2,
  Link as LinkIcon,
  FileDown,
  Loader2,
  Calendar,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import {
  usePublishRecord,
  useAssetPublishRecords,
} from './hooks/usePublish'
import { useAsset } from '../documents/hooks/useAsset'
import type { PublishRecord } from '@/types/api'
import { cn } from '@/lib/utils'

export default function PublishReceiptPage() {
  const { id: projectId, docId, publishId } = useParams<{
    id: string
    docId: string
    publishId: string
  }>()
  const navigate = useNavigate()
  const recordQuery = usePublishRecord(publishId)
  const historyQuery = useAssetPublishRecords(docId)
  const assetQuery = useAsset(docId)

  if (recordQuery.error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="加载发布记录失败"
        error={recordQuery.error}
        onRetry={() => recordQuery.refetch()}
        action={
          <button
            type="button"
            onClick={() => projectId && navigate(`/projects/${projectId}/documents`)}
            className="font-ui text-body-sm text-accent-primary-dark hover:underline"
          >
            返回文档列表
          </button>
        }
      />
    )
  }

  if (recordQuery.isLoading || !recordQuery.data) {
    return <LoadingSkeleton variant="document" />
  }

  const record = recordQuery.data
  const history = historyQuery.data ?? []

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <header className="flex items-center gap-3 border-b border-border-subtle bg-bg-card px-6 py-3">
        <button
          type="button"
          onClick={() => projectId && navigate(`/projects/${projectId}/documents/${docId}`)}
          className="font-ui text-caption text-text-muted hover:text-text-primary"
        >
          ← 返回文档
        </button>
        <h1 className="font-content text-h3 text-text-primary">
          发布回执 · {assetQuery.data?.title ?? '加载中…'}
        </h1>
      </header>

      <main className="overflow-auto bg-bg-page">
        <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
          {/* 大对勾 + 版本号 */}
          <section className="flex items-center gap-4 rounded-lg border border-success-border bg-success-bg/40 p-5">
            <div className="flex size-12 items-center justify-center rounded-full bg-success-bg">
              <CheckCircle2 className="size-7 text-success-dark" />
            </div>
            <div className="space-y-0.5">
              <h2 className="font-content text-h2 text-text-primary">发布成功</h2>
              <p className="font-ui text-caption text-text-muted">
                版本 <code className="font-mono text-text-secondary">v{record.asset_version}</code>{' '}
                · {formatDateTime(record.published_at)} · 发布人 {record.published_by}
              </p>
            </div>
          </section>

          {/* 当前 record 渠道详情 */}
          <section>
            <h3 className="mb-2 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
              本次发布
            </h3>
            <DestinationCard record={record} highlighted />
          </section>

          {/* 历史 */}
          {history.length > 1 ? (
            <section>
              <h3 className="mb-2 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
                历史发布记录
              </h3>
              <ul className="space-y-2">
                {history
                  .filter((h) => h.id !== record.id)
                  .map((h) => (
                    <li key={h.id}>
                      <DestinationCard record={h} />
                    </li>
                  ))}
              </ul>
            </section>
          ) : null}

          {/* 版本 diff (T12 §8) - MVP 跳过, 留 TODO */}
          <section className="rounded-md border border-dashed border-border-medium bg-bg-card p-4 text-center">
            <p className="font-ui text-caption text-text-muted">
              · 版本 diff (与上版本对比) 在后续迭代中接入 (npm i diff + line-by-line color render)
            </p>
            <p className="mt-1 font-ui text-micro text-text-subtle">
              · 撤回发布需结合 T13 凭证管理 (RBAC) 一起做
            </p>
          </section>
        </div>
      </main>
    </div>
  )
}

interface DestinationCardProps {
  record: PublishRecord
  highlighted?: boolean
}

function DestinationCard({ record, highlighted }: DestinationCardProps) {
  const [copied, setCopied] = useState(false)
  const meta = DESTINATION_META[record.destination] ?? {
    label: record.destination,
    Icon: ExternalLink,
  }
  const Icon = meta.Icon
  const statusMap = {
    success: { label: '成功', cls: 'bg-success-bg text-success-dark' },
    pending: { label: '发布中', cls: 'bg-info-bg text-info' },
    failed: { label: '失败', cls: 'bg-danger-bg text-danger' },
    revoked: { label: '已撤回', cls: 'bg-bg-warm text-text-muted' },
  } as const
  const status = statusMap[record.status]

  async function handleCopy() {
    if (!record.url) return
    try {
      await navigator.clipboard.writeText(record.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // navigator.clipboard 在 http context 可能不可用; fallback select+execCommand 略
    }
  }

  return (
    <div
      className={cn(
        'rounded-md border bg-bg-card p-4 transition',
        highlighted
          ? 'border-accent-primary-border bg-accent-primary-light/30'
          : 'border-border-subtle',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <Icon className="size-5 shrink-0 text-text-secondary mt-0.5" />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <p className="font-ui text-body-sm font-medium text-text-primary">
                {meta.label}
              </p>
              <span className={cn('rounded-full px-2 py-0.5 font-ui text-micro', status.cls)}>
                {status.label}
              </span>
              {record.visibility ? (
                <span className="rounded-full bg-info-bg px-2 py-0.5 font-ui text-micro text-info">
                  {record.visibility === 'team' ? '团队可见' : '公开可见'}
                </span>
              ) : null}
            </div>
            {record.url ? (
              <code className="block break-all rounded bg-bg-warm px-2 py-1 font-mono text-caption text-text-secondary">
                {record.url}
              </code>
            ) : null}
            <p className="font-ui text-micro text-text-subtle flex items-center gap-1">
              <Calendar className="size-3" />
              {formatDateTime(record.published_at)} · v{record.asset_version} · {record.publish_mode}
            </p>
            {record.error ? (
              <p className="font-ui text-caption text-danger">{record.error}</p>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-1.5">
          {record.url ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleCopy}
                className="font-ui text-caption"
              >
                {copied ? (
                  <>
                    <CheckCircle2 className="size-3" />
                    已复制
                  </>
                ) : (
                  <>
                    <Copy className="size-3" />
                    复制
                  </>
                )}
              </Button>
              {record.destination !== 'export_md' ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  asChild
                  className="font-ui text-caption"
                >
                  <a href={record.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="size-3" />
                    打开
                  </a>
                </Button>
              ) : null}
            </>
          ) : (
            <Button type="button" size="sm" variant="ghost" disabled className="font-ui text-caption">
              <Loader2 className="size-3 animate-spin" />
              准备中
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

const DESTINATION_META: Record<string, { label: string; Icon: typeof Building2 }> = {
  internal: { label: '站内文档库', Icon: Building2 },
  public_link: { label: '公开链接', Icon: LinkIcon },
  export_md: { label: 'Markdown 文件', Icon: FileDown },
  export_pdf: { label: 'PDF 文件', Icon: FileDown },
  export_docx: { label: 'DOCX 文件', Icon: FileDown },
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
