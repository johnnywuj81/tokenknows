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
import { Link, useNavigate, useParams } from 'react-router-dom'
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
import { useChapters } from '../documents/hooks/useChapters'
import { ChapterDiffView } from './components/ChapterDiffView'
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
  const chaptersQuery = useChapters(docId)

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
            <DestinationCard record={record} projectId={projectId ?? ''} highlighted />
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
                      <DestinationCard record={h} projectId={projectId ?? ''} />
                    </li>
                  ))}
              </ul>
            </section>
          ) : null}

          {/* P3 · 版本 diff: 章节级 line-by-line */}
          <section>
            <h3 className="mb-2 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
              章节级 diff (本版本 vs 重生成前)
            </h3>
            {chaptersQuery.isLoading ? (
              <p className="font-ui text-caption text-text-muted">加载章节…</p>
            ) : chaptersQuery.data && chaptersQuery.data.length > 0 ? (
              (() => {
                const diffable = chaptersQuery.data.filter(
                  (c) => c.regeneration_history.length > 0
                )
                if (diffable.length === 0) {
                  return (
                    <div className="rounded-md border border-dashed border-border-medium bg-bg-card p-4 text-center">
                      <p className="font-ui text-caption text-text-muted">
                        本文档章节未经重生成, 无 diff 历史. 编辑或重生成后可在此查看
                        与上版本的逐行差异.
                      </p>
                    </div>
                  )
                }
                return (
                  <ul className="space-y-2">
                    {chaptersQuery.data.map((c, idx) => (
                      <li key={c.id}>
                        <ChapterDiffView
                          chapter={c}
                          defaultExpanded={idx === 0 && diffable[0]?.id === c.id}
                        />
                      </li>
                    ))}
                  </ul>
                )
              })()
            ) : (
              <p className="font-ui text-caption text-text-muted">无章节数据</p>
            )}
            <p className="mt-3 font-ui text-micro text-text-subtle">
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
  projectId: string
  highlighted?: boolean
}

/**
 * T139 修: backend `record.url` 对 internal destination 是约定字符串
 * `/internal/assets/{asset_id}/v{N}` (generation_service.py:3088),
 * 既不是 backend 端点也不是前端路由 → 点 "打开" 会跳到 SPA fallback "/".
 * 这里把它转译成真实的前端 DocumentPage 路由.
 *
 * T144 (CRITICAL): 对外部 URL 增加 scheme 白名单. backend 数据 drift 或者
 * 被攻击者影响时, record.url 可能是 javascript:/data: URL, 直接放进 <a href>
 * 会被点击触发 XSS. 只允许 http(s); 其它 scheme 返 '#' 让 UI 隐藏按钮.
 */
function resolveOpenHref(record: PublishRecord, projectId: string): string {
  if (!record.url) return '#'
  if (
    record.destination === 'internal' &&
    record.url.startsWith('/internal/assets/')
  ) {
    return projectId
      ? `/projects/${projectId}/documents/${record.asset_id}`
      : '#'
  }
  // 站内相对路径放行 (以 / 开头), 走 react-router Link
  if (record.url.startsWith('/')) {
    return record.url
  }
  // 外部 URL: 必须 http(s), 其它 scheme (javascript:/data:/file: 等) 一律拒绝
  try {
    const { protocol } = new URL(record.url)
    if (protocol === 'http:' || protocol === 'https:') {
      return record.url
    }
  } catch {
    /* malformed URL → fall through to '#' */
  }
  return '#'
}

function DestinationCard({ record, projectId, highlighted }: DestinationCardProps) {
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
              {record.destination !== 'export_md' ? (() => {
                const href = resolveOpenHref(record, projectId)
                // T144 (MEDIUM-1): href === '#' 意味着 URL 缺失或 scheme 被
                // 拒绝 (见 resolveOpenHref). 渲染按钮只会跳到页顶迷惑用户, 干脆隐藏.
                if (href === '#') return null
                // T140: 站内路径用 react-router Link (同 tab, 不重载 SPA, 不踩 SW timing 坑);
                // 外部 URL 仍 <a target="_blank"> 新 tab.
                const isInternal = href.startsWith('/')
                return (
                  <Button type="button" size="sm" variant="ghost" asChild className="font-ui text-caption">
                    {isInternal ? (
                      <Link to={href}>
                        <ExternalLink className="size-3" />
                        打开
                      </Link>
                    ) : (
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="size-3" />
                        打开
                      </a>
                    )}
                  </Button>
                )
              })() : null}
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
