/**
 * IMDatasourcesPage · /projects/:id/datasources (v0.3 T24)
 *
 * MVP 实现:
 * - 顶栏显示 "数据源" 标题 + "添加 IM" 按钮 (打开向导)
 * - 列表区: 已有 IMConnection 卡片 (含 platform / tenant / status)
 * - 向导对话框: 选 platform → 创建 pending connection → 显示 authorize_url
 *
 * 不在 MVP 内 (留 v0.3.1):
 * - 视觉精修 / mockup
 * - SSE 监听飞书 auth-callback (用户回来后刷新 list 即可)
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Plus, ExternalLink, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import {
  useCreateIMConnection,
  useIMConnections,
  useRevokeIMConnection,
} from './hooks/useIMConnections'
import type { IMPlatform } from '@/types/api'

const PLATFORM_LABELS: Record<IMPlatform, string> = {
  feishu: '飞书 / Lark',
  dingtalk: '钉钉',
  wework: '企业微信',
  email: '邮件 (IMAP)',
}

export default function IMDatasourcesPage() {
  const { id: projectId = '' } = useParams<{ id: string }>()
  const [wizardOpen, setWizardOpen] = useState(false)
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const [platform, setPlatform] = useState<IMPlatform>('feishu')

  const conns = useIMConnections(projectId)
  const create = useCreateIMConnection(projectId)
  const revoke = useRevokeIMConnection(projectId)

  if (conns.isLoading) return <LoadingSkeleton variant="list" />
  if (conns.isError) {
    return (
      <ErrorState
        title="加载 IM 数据源失败"
        description="网络错误或后端未启动"
        onRetry={() => conns.refetch()}
      />
    )
  }

  const handleCreate = async () => {
    const result = await create.mutateAsync({ platform })
    setAuthUrl(result.authorize_url)
  }

  const closeWizard = () => {
    setWizardOpen(false)
    setAuthUrl(null)
  }

  const data = conns.data ?? []

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="font-content text-2xl font-semibold text-text-primary">
            IM 数据源
          </h1>
          <p className="font-ui text-sm text-text-secondary">
            连接飞书 / 钉钉 / 企微 / 邮件,自动蒸馏对话中的价值片段
          </p>
        </div>
        <Button onClick={() => setWizardOpen(true)}>
          <Plus className="size-4" />
          添加 IM
        </Button>
      </header>

      {data.length === 0 ? (
        <EmptyState
          title="还没有 IM 数据源"
          description="点击右上角'添加 IM' 完成 3 步授权"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((c) => (
            <Card key={c.id} className="flex flex-col gap-3 p-4">
              <div className="flex items-baseline justify-between">
                <span className="font-content text-lg font-semibold text-text-primary">
                  {PLATFORM_LABELS[c.platform]}
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${
                    c.status === 'active'
                      ? 'bg-success-light text-success-dark'
                      : c.status === 'pending'
                        ? 'bg-warning-light text-warning-dark'
                        : 'bg-bg-warm text-text-tertiary'
                  }`}
                >
                  {c.status}
                </span>
              </div>
              <p className="font-ui text-sm text-text-secondary">
                {c.tenant_name ?? '租户未知'}
              </p>
              {c.consent_signed_at && (
                <p className="font-ui text-xs text-text-tertiary">
                  授权于 {new Date(c.consent_signed_at).toLocaleDateString('zh-CN')}
                </p>
              )}
              <div className="mt-auto flex gap-2">
                {c.status === 'active' && (
                  <Button asChild variant="outline" size="sm">
                    <Link to={`/projects/${projectId}/datasources/im/connections/${c.id}/chats`}>
                      管理群
                    </Link>
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => revoke.mutate(c.id)}
                  disabled={revoke.isPending || c.status === 'revoked'}
                >
                  <Trash2 className="size-4" />
                  撤回
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* 向导对话框 */}
      <Dialog open={wizardOpen} onOpenChange={(o) => !o && closeWizard()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加 IM 数据源</DialogTitle>
            <DialogDescription>
              {authUrl
                ? '点击下方链接完成 OAuth 授权,授权后系统会自动激活连接'
                : '选择平台,系统会创建一条 pending 连接,然后你需要完成 OAuth 授权'}
            </DialogDescription>
          </DialogHeader>

          {!authUrl ? (
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label>平台</Label>
                <Select
                  value={platform}
                  onValueChange={(v) => setPlatform(v as IMPlatform)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(PLATFORM_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 py-4">
              {authUrl.startsWith('#im-not-configured') ? (
                <div className="rounded border border-warning-light bg-warning-light/30 p-3 font-mono text-sm text-warning-dark">
                  后端凭据未配置,请管理员在 .env 设置 FEISHU_APP_ID / FEISHU_APP_SECRET 后重启。
                </div>
              ) : (
                <a
                  href={authUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 rounded border border-accent-primary bg-accent-primary-light/40 p-3 font-ui text-sm text-accent-primary-dark hover:underline"
                >
                  <ExternalLink className="size-4" />
                  前往 {PLATFORM_LABELS[platform]} 授权
                </a>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={closeWizard}>
              {authUrl ? '完成' : '取消'}
            </Button>
            {!authUrl && (
              <Button
                onClick={handleCreate}
                disabled={create.isPending}
              >
                {create.isPending ? '创建中...' : '获取授权链接'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
