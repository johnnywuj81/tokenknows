/**
 * McpAccessPanel · Phase B 「MCP 接入」自助 API token + env 配置块.
 *
 * 三段式:
 *   1. token 列表 (name / 前缀 / 创建时间 / 最后使用 / 撤销)
 *   2. 创建表单 + 一次性明文展示卡 (明文只显示这一次)
 *   3. 可复制的 env 配置块 (TOKENKNOWS_API_BASE / API_TOKEN / DEFAULT_PROJECT)
 *
 * 明文 token 只存在于本组件 useState; 下次创建覆盖, unmount 即清.
 */

import { useRef, useState } from 'react'
import { Check, Copy, KeyRound, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState } from '@/components/shared/EmptyState'
import { TokenDisplay } from '@/components/shared/TokenDisplay'
import type { ApiTokenPublic, CreateApiTokenResponse } from '@/types/api'
import {
  useApiTokens,
  useCreateApiToken,
  useRevokeApiToken,
} from '../hooks/useApiTokens'

interface McpAccessPanelProps {
  projectId: string
}

const DEFAULT_API_BASE = import.meta.env.DEV
  ? 'http://localhost:8001'
  : window.location.origin

export function McpAccessPanel({ projectId }: McpAccessPanelProps) {
  const q = useApiTokens()
  // 一次性明文: 只活在本组件 state, 下次创建覆盖 / unmount 清除
  const [created, setCreated] = useState<CreateApiTokenResponse | null>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)

  if (q.isLoading) {
    return <p className="text-sm text-text-secondary">加载中...</p>
  }
  if (q.isError || !q.data) {
    return (
      <div className="flex items-center gap-2 text-sm text-danger">
        <span>加载 API token 失败.</span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => q.refetch()}
        >
          重试
        </Button>
      </div>
    )
  }

  const items = q.data.items
  const isEmpty = items.length === 0

  return (
    <section className="space-y-4" data-testid="mcp-access-panel">
      <header>
        <h2 className="font-content text-h2 text-text-primary">MCP 接入</h2>
        <p className="font-ui text-caption text-text-muted">
          创建个人 API token, 把 TokenKnows MCP server 接入 Claude Code /
          Cursor 等客户端.
        </p>
      </header>

      {/* ── 1. token 列表 ───────────────────────────────────── */}
      {isEmpty ? (
        <div
          className="rounded-md border border-border-subtle bg-bg-card"
          data-testid="tokens-empty"
        >
          <EmptyState
            icon={<KeyRound className="size-12" />}
            title="还没有 API token"
            description="创建一个 token, 复制下方 env 配置即可让 MCP server 访问本实例."
            action={{
              label: '创建第一个 API token',
              onClick: () => nameInputRef.current?.focus(),
            }}
          />
        </div>
      ) : (
        <div
          className="overflow-hidden rounded-md border border-border-subtle bg-bg-card"
          data-testid="tokens-table"
        >
          <table className="w-full font-ui text-body-sm">
            <thead className="border-b border-border-subtle bg-bg-warm">
              <tr className="text-left text-caption text-text-muted">
                <th className="px-3 py-2">名称</th>
                <th className="px-3 py-2">前缀</th>
                <th className="px-3 py-2">创建时间</th>
                <th className="px-3 py-2">最后使用</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <TokenRow key={t.id} token={t} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 2. 创建表单 + 一次性明文卡 ──────────────────────── */}
      <CreateTokenForm
        nameInputRef={nameInputRef}
        onCreated={setCreated}
      />
      {created ? <RevealCard created={created} /> : null}

      {/* ── 3. env 配置块 ───────────────────────────────────── */}
      <EnvBlock projectId={projectId} plainToken={created?.token ?? null} />
    </section>
  )
}

// ─── Subcomponents ──────────────────────────────────────────

function TokenRow({ token }: { token: ApiTokenPublic }) {
  const revoke = useRevokeApiToken()

  function handleRevoke(): void {
    const ok = window.confirm(
      `确认撤销 token "${token.name}"? 使用它的 MCP 连接将立即失效, 此操作不可逆.`,
    )
    if (!ok) return
    revoke.mutate(token.id)
  }

  return (
    <tr
      className="border-b border-border-subtle last:border-b-0"
      data-testid={`token-row-${token.id}`}
    >
      <td className="px-3 py-2 text-text-primary">{token.name}</td>
      <td className="px-3 py-2 font-mono text-text-secondary">
        {token.token_prefix}
      </td>
      <td className="px-3 py-2 font-mono text-caption text-text-subtle">
        {new Date(token.created_at).toLocaleDateString('zh-CN')}
      </td>
      <td className="px-3 py-2 font-mono text-caption text-text-subtle">
        {token.last_used_at
          ? new Date(token.last_used_at).toLocaleDateString('zh-CN')
          : '从未使用'}
      </td>
      <td className="px-3 py-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={handleRevoke}
          disabled={revoke.isPending}
          data-testid={`revoke-${token.id}`}
        >
          {revoke.isPending ? '撤销中...' : '撤销'}
        </Button>
      </td>
    </tr>
  )
}


function CreateTokenForm({
  nameInputRef,
  onCreated,
}: {
  nameInputRef: React.RefObject<HTMLInputElement | null>
  onCreated: (res: CreateApiTokenResponse) => void
}) {
  const create = useCreateApiToken()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('请输入 token 名称')
      return
    }
    try {
      const res = await create.mutateAsync({ name: name.trim() })
      onCreated(res)
      setName('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '创建失败')
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-canvas p-3 sm:flex-row sm:items-center"
      data-testid="create-token-form"
    >
      <Input
        ref={nameInputRef}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="token 名称 (如 my-macbook)"
        maxLength={100}
        data-testid="create-token-name"
        className="flex-1"
      />
      <Button
        type="submit"
        size="sm"
        disabled={create.isPending}
        data-testid="create-token-submit"
      >
        {create.isPending ? '创建中...' : '+ 创建 token'}
      </Button>
      {error && (
        <p className="text-xs text-danger" data-testid="create-token-error">
          {error}
        </p>
      )}
    </form>
  )
}


function RevealCard({ created }: { created: CreateApiTokenResponse }) {
  return (
    <div
      className="space-y-3 rounded-md border border-warning bg-warning-bg p-4"
      data-testid="token-reveal"
    >
      <p className="flex items-center gap-1.5 font-ui text-sm font-medium text-warning-dark">
        <TriangleAlert className="size-4 shrink-0" />
        token 只显示这一次, 请立即复制
      </p>
      <TokenDisplay
        token={created.token}
        label={`API token · ${created.item.name}`}
        helpText="填到插件的 TOKENKNOWS_API_TOKEN。明文不会再次显示; 丢了就撤销这个 token 重新创建。"
      />
    </div>
  )
}


function EnvBlock({
  projectId,
  plainToken,
}: {
  projectId: string
  plainToken: string | null
}) {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE)
  const [copied, setCopied] = useState(false)

  const envText = [
    `TOKENKNOWS_API_BASE=${apiBase}`,
    `TOKENKNOWS_API_TOKEN=${plainToken ?? 'tkk_********'}`,
    `TOKENKNOWS_DEFAULT_PROJECT=${projectId}`,
  ].join('\n')

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(envText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard 不可用 (非 https / 老浏览器) — 用户可手动选中 <pre> 复制
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-border-subtle bg-bg-card p-4">
      <h3 className="font-content text-h3 text-text-primary">env 配置</h3>
      <div className="space-y-1.5">
        <label
          htmlFor="mcp-api-base"
          className="font-ui text-caption text-text-secondary"
        >
          API Base
        </label>
        <Input
          id="mcp-api-base"
          type="text"
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          data-testid="env-api-base"
          className="font-mono"
        />
        <p className="text-caption text-text-subtle">
          本机开发默认 http://localhost:8001; 部署后改成实例对外地址.
        </p>
      </div>
      <pre
        className="overflow-x-auto rounded bg-inverse-bg px-3 py-2 font-mono text-caption text-inverse-text"
        data-testid="env-block"
      >
        {envText}
      </pre>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="font-ui"
          onClick={handleCopy}
          disabled={!plainToken}
          data-testid="copy-env-btn"
        >
          {copied ? (
            <>
              <Check className="size-3.5 text-success" />
              已复制
            </>
          ) : (
            <>
              <Copy className="size-3.5" />
              复制配置
            </>
          )}
        </Button>
        {!plainToken ? (
          <span className="font-ui text-caption text-text-subtle">
            先创建一个 token, 明文在手时才能复制完整配置.
          </span>
        ) : null}
      </div>
    </div>
  )
}
