/**
 * T14 · LlmEgressPanel (在 T13 设置 Tab 内)
 *
 * 三层出域开关 (instance ∧ project ∧ task) + 模型 allowlist + 审计级别.
 *
 * MVP:
 *   - 三层 toggle 默认 ON, 是只读 (实际由 .env.local 控制, 不暴露 PATCH)
 *   - 模型 allowlist 展示 4 个 provider 状态 (Anthropic/OpenAI/MiniMax/Ollama)
 *   - 审计级别 read-only summary
 *   - "dry-run preview" 按钮调 GET /llm/egress/preview (T14 §10 红线)
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, ShieldOff, Beaker, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

// T109 · 真实 provider 状态 (取自 backend)
interface ApiProviderStatus {
  name: 'anthropic' | 'openai' | 'minimax' | 'ollama'
  models: string[]
  configured: boolean
  status: 'configured' | 'key_missing'
}

function useProviderStatus() {
  return useQuery({
    queryKey: ['llm', 'providers', 'status'],
    queryFn: async () => {
      const { data } = await api.get<ApiProviderStatus[]>('/llm/providers/status')
      return data
    },
    staleTime: 60_000,
  })
}

interface LlmEgressPanelProps {
  projectId: string | undefined
}

interface PreviewResponse {
  will_send: boolean
  provider: string
  model: string
  estimated_input_tokens: number
  estimated_output_tokens: number
  egress_check: {
    instance: boolean
    project: boolean
    task: boolean
    all_pass: boolean
  }
  blocking_reason?: string | null
}

export function LlmEgressPanel({ projectId }: LlmEgressPanelProps) {
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  async function handlePreview() {
    setPreviewing(true)
    setPreviewError(null)
    try {
      const { data } = await api.post<PreviewResponse>('/llm/egress/preview', {
        task: 'weekly_report',
        messages: [
          {
            role: 'user',
            content:
              '本周 EgressGate PR 合并完成, 系统接入了三层出域门禁. 请生成本章节草稿.',
          },
        ],
        project_id: projectId,
      })
      setPreview(data)
    } catch (err) {
      const { getErrorMessage } = await import('@/lib/api')
      setPreviewError(getErrorMessage(err))
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="font-content text-h2 text-text-primary">LLM 与出域</h2>
        <p className="font-ui text-caption text-text-muted">
          三层出域开关 (instance ∧ project ∧ task) + 模型 allowlist + 审计.
          MVP 阶段策略由 .env.local 配置, UI 仅展示当前状态.
        </p>
      </header>

      {/* 三层 toggle */}
      <section className="rounded-md border border-border-subtle bg-bg-card p-4 space-y-3">
        <h3 className="font-content text-h3 text-text-primary">三层出域门禁</h3>
        <p className="font-ui text-caption text-text-muted">
          全部为 ON 才允许云端 LLM 调用 (anthropic/openai/minimax/ollama).
          任一 OFF, router._egress_check 抛 EgressDeniedError.
        </p>
        <ul className="space-y-2">
          <EgressTier name="instance" label="实例级 (instance)" desc="管理员控制. 关闭后全实例所有项目无法出域." enabled={true} />
          <EgressTier name="project" label="项目级 (project)" desc="项目 owner 控制. 关闭后本项目无法出域." enabled={true} />
          <EgressTier name="task" label="任务级 (task)" desc="可按 task 类型细分. 默认全允许." enabled={true} />
        </ul>
      </section>

      {/* 模型 allowlist (T109 真实状态 from backend) */}
      <ProviderAllowlist />

      {/* 审计 */}
      <section className="rounded-md border border-border-subtle bg-bg-card p-4 space-y-2">
        <h3 className="font-content text-h3 text-text-primary">审计</h3>
        <p className="font-ui text-caption text-text-muted">
          每次云端 LLM 调用都会写入 <code className="font-mono">data/egress.sqlite</code>
          的 egress_log 表 (provider/model/tokens/cost/hash/fallback_used).
        </p>
        <p className="font-ui text-caption">
          级别:
          <span className="ml-1 rounded-full bg-success-bg px-2 py-0.5 text-success-dark">full (完整审计)</span>
        </p>
      </section>

      {/* dry-run preview */}
      <section className="rounded-md border border-info-border bg-info-bg/30 p-4 space-y-2">
        <h3 className="flex items-center gap-2 font-content text-h3 text-info">
          <Beaker className="size-4" />
          Dry-run Preview · 出域影响预测
        </h3>
        <p className="font-ui text-caption text-text-muted">
          架构红线: 不能让用户"以为没出域, 其实出了". 本按钮不真调云端,
          只返回"如果开启会发哪些字段去哪 provider".
        </p>
        <Button
          type="button"
          onClick={handlePreview}
          disabled={previewing}
          variant="outline"
          className="font-ui"
        >
          {previewing ? <Loader2 className="size-3.5 animate-spin" /> : <Beaker className="size-3.5" />}
          预测 (task=weekly_report)
        </Button>
        {previewError ? (
          <p className="font-ui text-caption text-danger">{previewError}</p>
        ) : null}
        {preview ? (
          <pre className="overflow-auto rounded-md border border-border-subtle bg-bg-page px-3 py-2 font-mono text-micro text-text-secondary">
            {JSON.stringify(preview, null, 2)}
          </pre>
        ) : null}
      </section>
    </section>
  )
}

interface EgressTierProps {
  name: string
  label: string
  desc: string
  enabled: boolean
}

function EgressTier({ name, label, desc, enabled }: EgressTierProps) {
  return (
    <li className="flex items-start justify-between gap-3 rounded-md border border-border-subtle bg-bg-card p-3">
      <div className="flex items-start gap-2">
        {enabled ? (
          <ShieldCheck className="size-4 mt-0.5 text-success-dark shrink-0" />
        ) : (
          <ShieldOff className="size-4 mt-0.5 text-danger shrink-0" />
        )}
        <div>
          <p className="font-ui text-body-sm font-medium text-text-primary">{label}</p>
          <p className="font-ui text-caption text-text-muted">{desc}</p>
          <p className="mt-0.5 font-mono text-micro text-text-subtle">env: {envVar(name)}</p>
        </div>
      </div>
      <span
        className={cn(
          'shrink-0 rounded-full px-2 py-0.5 font-ui text-micro',
          enabled ? 'bg-success-bg text-success-dark' : 'bg-danger-bg text-danger',
        )}
      >
        {enabled ? 'ENABLED' : 'DISABLED'}
      </span>
    </li>
  )
}

function envVar(tier: string): string {
  if (tier === 'instance') return 'INSTANCE_EGRESS_ENABLED'
  if (tier === 'project') return 'DEFAULT_PROJECT_EGRESS_ENABLED'
  return 'TASK_<TASK>_PROVIDER'
}

/** T109 · 真实状态 (取自 backend GET /llm/providers/status). */
function ProviderAllowlist() {
  const q = useProviderStatus()
  return (
    <section className="rounded-md border border-border-subtle bg-bg-card p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-content text-h3 text-text-primary">允许的 provider / 模型</h3>
        <p className="font-ui text-caption text-text-muted">
          仅看 key 是否配置 (configured); 真可达性需调 Dry-run preview 验证.
        </p>
      </div>
      {q.isLoading ? (
        <p className="font-ui text-caption text-text-muted">检测中…</p>
      ) : q.error ? (
        <p className="font-ui text-caption text-danger">
          状态查询失败: {q.error instanceof Error ? q.error.message : '未知'}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {(q.data ?? []).map((p) => (
            <ProviderRow
              key={p.name}
              name={p.name}
              models={p.models}
              status={p.status === 'configured' ? 'configured_only' : 'key_missing'}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

interface ProviderRowProps {
  name: string
  models: string[]
  status: 'active' | 'reachable_no_vpn' | 'key_invalid' | 'configured_only' | 'key_missing'
}

function ProviderRow({ name, models, status }: ProviderRowProps) {
  const statusMap = {
    active: { label: '在线', cls: 'bg-success-bg text-success-dark' },
    reachable_no_vpn: { label: '本机网络不通', cls: 'bg-warning-bg text-warning' },
    key_invalid: { label: 'Key 无效', cls: 'bg-danger-bg text-danger' },
    configured_only: { label: '已配置', cls: 'bg-success-bg text-success-dark' },
    key_missing: { label: '未配置 API key', cls: 'bg-warning-bg text-warning-dark' },
  } as const
  const s = statusMap[status]
  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-bg-card px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-body-sm text-text-primary">{name}</p>
        <p className="font-ui text-micro text-text-subtle">
          {models.length > 0 ? models.join(' · ') : '(无 model)'}
        </p>
      </div>
      <span className={cn('shrink-0 rounded-full px-2 py-0.5 font-ui text-micro', s.cls)}>
        {s.label}
      </span>
    </li>
  )
}
