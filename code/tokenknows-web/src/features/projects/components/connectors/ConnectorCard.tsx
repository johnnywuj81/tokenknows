/**
 * ConnectorCard · Step 3 通用包装(标题 + icon + 状态徽标 + body slot)
 */

import type { ReactNode } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

type ConnectorState = 'pending' | 'in_progress' | 'connected' | 'failed'

interface ConnectorCardProps {
  icon: React.ComponentType<{ className?: string }>
  title: string
  state: ConnectorState
  children: ReactNode
}

const stateLabels: Record<ConnectorState, string> = {
  pending: '待配置',
  in_progress: '配置中',
  connected: '已连接',
  failed: '失败',
}

export function ConnectorCard({ icon: Icon, title, state, children }: ConnectorCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border bg-bg-card p-4 transition',
        state === 'connected' ? 'border-success-border' : 'border-border-subtle',
      )}
    >
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="size-4 text-text-secondary" />
          <h3 className="font-ui text-body font-medium text-text-primary">{title}</h3>
        </div>
        <Badge state={state} />
      </header>
      <div>{children}</div>
    </div>
  )
}

function Badge({ state }: { state: ConnectorState }) {
  const map: Record<ConnectorState, { className: string; icon?: React.ReactNode }> = {
    pending: { className: 'bg-bg-warm text-text-muted' },
    in_progress: {
      className: 'bg-info-bg text-info',
      icon: <Loader2 className="size-3 animate-spin" />,
    },
    connected: {
      className: 'bg-success-bg text-success-dark',
      icon: <Check className="size-3" />,
    },
    failed: { className: 'bg-danger-bg text-danger' },
  }
  const config = map[state]
  return (
    <span
      className={cn(
        'flex items-center gap-1 rounded px-1.5 py-0.5 font-ui text-micro font-medium',
        config.className,
      )}
    >
      {config.icon}
      {stateLabels[state]}
    </span>
  )
}
