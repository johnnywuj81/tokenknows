/**
 * PublishDialog · T11 发布对话框
 *
 * 入口: DocumentPage / RedactionPage 完成后点"发布"
 *
 * 当前支持的渠道:
 *   - 站内文档库 (internal)
 *   - 公开链接 (public_link) + visibility radio
 *   - 导出 Markdown (export_md)
 *
 * MVP 不做的:
 *   - PDF / DOCX 渲染 (后端 docling 集成留 W4D19)
 *   - Feishu / Slack / Notion 推送 (T13 凭证完成后)
 *   - 链接过期日期 (T14 凭证策略再加)
 *
 * 成功后 navigate 到 T12 receipt 页 (第一条 record).
 */

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Send,
  Loader2,
  AlertCircle,
  ShieldAlert,
  CheckCircle2,
  Building2,
  Link as LinkIcon,
  FileDown,
} from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { usePublishAsset } from './hooks/usePublish'
import { useAsset } from '../documents/hooks/useAsset'
import { getErrorMessage } from '@/lib/api'
import type { PublishDestination } from '@/types/api'
import { cn } from '@/lib/utils'

interface PublishDialogProps {
  assetId: string | null | undefined
}

interface DestinationChoice {
  value: PublishDestination
  label: string
  description: string
  icon: typeof Building2
}

const DESTINATIONS: DestinationChoice[] = [
  {
    value: 'internal',
    label: '站内文档库',
    description: '团队成员可在 TokenKnows 内访问. 不出实例.',
    icon: Building2,
  },
  {
    value: 'public_link',
    label: '公开链接',
    description: '生成不可猜测的分享 URL. 可选 Team / Public visibility.',
    icon: LinkIcon,
  },
  {
    value: 'export_md',
    label: '导出 Markdown',
    description: '生成可下载的 .md 文件. 不联网, 完全本地.',
    icon: FileDown,
  },
]

export function PublishDialog({ assetId }: PublishDialogProps) {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const open = useDocumentUiStore((s) => s.publishOpen)
  const close = useDocumentUiStore((s) => s.closePublish)
  const assetQuery = useAsset(assetId)
  const publish = usePublishAsset()

  const [destination, setDestination] = useState<PublishDestination>('internal')
  const [visibility, setVisibility] = useState<'team' | 'public'>('team')
  const [confirmChecked, setConfirmChecked] = useState(false)

  const asset = assetQuery.data
  const blocked = asset
    ? asset.status !== 'approved' && asset.status !== 'draft'
    : true
  const blockReason = blockReasonFor(asset?.status, asset?.approval_state)
  const canSubmit =
    !!assetId && !blocked && confirmChecked && !publish.isPending

  function handleOpenChange(o: boolean) {
    if (!o && !publish.isPending) {
      setDestination('internal')
      setVisibility('team')
      setConfirmChecked(false)
      publish.reset()
      close()
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!assetId || !canSubmit || !projectId) return
    try {
      const records = await publish.mutateAsync({
        assetId,
        destinations: [destination],
        publishMode: 'full',
        visibility: destination === 'public_link' ? visibility : null,
      })
      const firstRecord = records[0]
      if (firstRecord) {
        navigate(`/projects/${projectId}/documents/${assetId}/published/${firstRecord.id}`)
      }
      // reset 状态在关闭时统一做
      setDestination('internal')
      setVisibility('team')
      setConfirmChecked(false)
      publish.reset()
      close()
    } catch {
      // 错误经 publish.error 显示
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-content">
              <Send className="size-4" />
              发布文档
            </DialogTitle>
            <DialogDescription className="font-ui text-caption text-text-muted">
              {asset
                ? `《${asset.title}》 · v${asset.current_version || 1}`
                : '加载中…'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {blocked && blockReason ? (
              <div className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-warning">
                <ShieldAlert className="size-4 mt-0.5 shrink-0" />
                <div className="space-y-0.5">
                  <p className="font-ui text-body-sm font-medium">{blockReason.title}</p>
                  <p className="font-ui text-caption">{blockReason.detail}</p>
                </div>
              </div>
            ) : null}

            {/* 渠道选择 */}
            <fieldset>
              <legend className="font-ui text-caption font-medium text-text-secondary">
                发布渠道
              </legend>
              <div className="mt-2 space-y-2">
                {DESTINATIONS.map((d) => {
                  const Icon = d.icon
                  const selected = destination === d.value
                  return (
                    <label
                      key={d.value}
                      className={cn(
                        'flex cursor-pointer items-start gap-3 rounded-md border p-3 transition',
                        selected
                          ? 'border-accent-primary bg-accent-primary-light'
                          : 'border-border-subtle bg-bg-card hover:border-border-medium',
                      )}
                    >
                      <input
                        type="radio"
                        name="destination"
                        value={d.value}
                        checked={selected}
                        onChange={() => setDestination(d.value)}
                        disabled={publish.isPending}
                        className="mt-1 size-4 accent-accent-primary"
                      />
                      <Icon
                        className={cn(
                          'size-4 mt-0.5 shrink-0',
                          selected ? 'text-accent-primary-dark' : 'text-text-secondary',
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-ui text-body-sm font-medium text-text-primary">
                          {d.label}
                        </p>
                        <p className="font-ui text-caption text-text-muted">
                          {d.description}
                        </p>
                      </div>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            {/* 公开链接 visibility */}
            {destination === 'public_link' ? (
              <fieldset>
                <legend className="font-ui text-caption font-medium text-text-secondary">
                  可见范围
                </legend>
                <div className="mt-2 flex gap-2">
                  {(['team', 'public'] as const).map((v) => (
                    <label
                      key={v}
                      className={cn(
                        'flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-md border px-3 py-2 transition',
                        visibility === v
                          ? 'border-accent-primary bg-accent-primary-light'
                          : 'border-border-subtle bg-bg-card hover:border-border-medium',
                      )}
                    >
                      <input
                        type="radio"
                        name="visibility"
                        value={v}
                        checked={visibility === v}
                        onChange={() => setVisibility(v)}
                        disabled={publish.isPending}
                        className="size-3 accent-accent-primary"
                      />
                      <span className="font-ui text-caption">
                        {v === 'team' ? '团队内 (需登录)' : '公开 (任何人可访问)'}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}

            {/* 确认清单 */}
            <label
              className={cn(
                'flex cursor-pointer items-start gap-2 rounded-md border border-border-subtle bg-bg-card p-3',
                publish.isPending && 'opacity-60',
              )}
            >
              <input
                type="checkbox"
                checked={confirmChecked}
                onChange={(e) => setConfirmChecked(e.target.checked)}
                disabled={publish.isPending}
                className="mt-0.5 size-4 accent-accent-primary"
              />
              <div className="space-y-1">
                <p className="font-ui text-body-sm font-medium text-text-primary">
                  我已确认
                </p>
                <ul className="space-y-0.5 font-ui text-caption text-text-muted">
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="size-3 text-success-dark" />
                    本文档已完成脱敏 (PII/Token/IP/内部代号)
                  </li>
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="size-3 text-success-dark" />
                    本文档已通过审批
                  </li>
                  {destination === 'public_link' ? (
                    <li className="flex items-center gap-1.5">
                      <ShieldAlert className="size-3 text-warning" />
                      公开后链接外泄无法收回, 已知悉风险
                    </li>
                  ) : null}
                </ul>
              </div>
            </label>

            {publish.error ? (
              <div className="flex items-start gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-danger">
                <AlertCircle className="size-4 mt-0.5 shrink-0" />
                <p className="font-ui text-body-sm">{getErrorMessage(publish.error)}</p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleOpenChange(false)}
              disabled={publish.isPending}
              className="font-ui"
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={!canSubmit}
              className="font-ui"
            >
              {publish.isPending ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  发布中…
                </>
              ) : (
                <>
                  <Send className="size-3.5" />
                  确认发布
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function blockReasonFor(
  status?: string,
  approval?: string,
): { title: string; detail: string } | null {
  if (!status) return null
  if (status === 'generating') {
    return { title: '文档仍在生成中', detail: '请等待 5 阶段流水线完成后再发布。' }
  }
  if (status === 'in_review') {
    return { title: '文档正在审批', detail: '需所有章节通过审批后再发布。' }
  }
  if (status === 'archived') {
    return { title: '文档已归档', detail: '归档后不可发布, 请克隆为新版本。' }
  }
  if (status === 'published') {
    return { title: '文档已发布', detail: '再次发布会创建新版本记录, 旧链接保留。' }
  }
  if (approval === 'rejected') {
    return { title: '文档被退回', detail: '部分章节被审批退回, 需先调整。' }
  }
  return null
}
