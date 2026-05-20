/**
 * EmptyWorkbench · 无项目时的全屏空态
 */

import { useNavigate } from 'react-router-dom'
import { Sparkles, ArrowRight, Lock, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function EmptyWorkbench() {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-8">
      <div className="max-w-xl text-center">
        <Sparkles className="mx-auto size-12 text-accent-primary" />
        <h1 className="mt-6 font-content text-h1 text-text-primary">建立你的研发知识空间</h1>
        <p className="mt-3 text-body text-text-muted">
          连接 Claude Code / GitHub 等数据源, 系统将自动采集事件, 24 小时内生成首份周报草稿。
        </p>

        <div className="mt-8 grid gap-3 text-left sm:grid-cols-2">
          <Feature
            icon={GitBranch}
            title="多源同步"
            text="Claude Code / Cursor / VS Code / GitHub PAT"
          />
          <Feature
            icon={Lock}
            title="默认零出域"
            text="三层开关 + 完整审计 + 客户密钥客户管"
          />
        </div>

        <Button
          className="mt-8 font-ui"
          onClick={() => navigate('/projects/new')}
        >
          + 新建项目
          <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}

function Feature({
  icon: Icon,
  title,
  text,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  text: string
}) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-card p-3">
      <div className="flex items-center gap-2 text-text-primary">
        <Icon className="size-4 text-accent-primary-dark" />
        <span className="font-ui text-body-sm font-medium">{title}</span>
      </div>
      <p className="mt-1 text-caption text-text-muted">{text}</p>
    </div>
  )
}
