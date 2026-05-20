/**
 * Placeholder · 临时占位页,用于 W1D1 地基日完成后、各任务页未实现时。
 * 各任务对应 page 实现时直接删除该 import,改成真实组件。
 */

import { Link } from 'react-router-dom'
import { Construction } from 'lucide-react'

interface PlaceholderProps {
  task: string          // e.g. "T01 · 登录"
  taskFile: string      // e.g. "T01-auth.md"
  description?: string
}

export function Placeholder({ task, taskFile, description }: PlaceholderProps) {
  return (
    <div className="p-8">
      <div className="mx-auto max-w-2xl rounded-lg border border-border-subtle bg-bg-card p-6 shadow-elev-1">
        <div className="mb-3 flex items-center gap-2 text-warning">
          <Construction className="size-4" />
          <span className="font-ui text-eyebrow uppercase tracking-wider">施工占位</span>
        </div>
        <h1 className="font-content text-h2 text-text-primary">{task}</h1>
        {description ? (
          <p className="mt-2 text-body text-text-muted">{description}</p>
        ) : null}
        <p className="mt-4 font-mono text-caption text-text-subtle">
          → engineering_handoff/tasks/{taskFile}
        </p>
        <Link
          to="/"
          className="mt-4 inline-block font-ui text-body-sm text-accent-primary-dark hover:underline"
        >
          ← 返回工作台
        </Link>
      </div>
    </div>
  )
}
