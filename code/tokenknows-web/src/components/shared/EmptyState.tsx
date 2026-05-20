/**
 * EmptyState · 数据为空时的占位组件。
 *
 * 设计依据: SharedFoundations.md §3.2
 *
 * 用法:
 *   <EmptyState
 *     icon={<FolderOpen className="size-12" />}
 *     title="还没有项目"
 *     description="新建一个项目,接入数据源后即可看到事件流"
 *     action={{ label: '+ 新建项目', onClick: () => navigate('/projects/new') }}
 *   />
 */

import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 p-8 text-center',
        className,
      )}
    >
      {icon ? <div className="text-text-subtle">{icon}</div> : null}
      <h3 className="font-content text-h3 text-text-primary">{title}</h3>
      {description ? (
        <p className="text-body text-text-muted max-w-md">{description}</p>
      ) : null}
      {action ? (
        <Button onClick={action.onClick} className="mt-2 font-ui">
          {action.label}
        </Button>
      ) : null}
    </div>
  )
}
