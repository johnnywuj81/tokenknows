/**
 * Step 4 · 完成页 + 跳工作台
 *
 * 显示已接入的数据源 + 跳工作台 CTA。
 */

import { CheckCircle2, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Datasource, Project } from '@/types/api'

interface StepDoneProps {
  project: Project
  addedDatasources: Datasource[]
  onGoToWorkbench: () => void
}

const TYPE_LABEL: Record<string, string> = {
  claude_code: 'Claude Code',
  cursor: 'Cursor',
  vscode: 'VS Code',
  github: 'GitHub',
  local_file: '本地文件',
}

export function StepDone({ project, addedDatasources, onGoToWorkbench }: StepDoneProps) {
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3 rounded-lg border border-success-border bg-success-bg p-4">
        <CheckCircle2 className="size-6 shrink-0 text-success" />
        <div className="space-y-1">
          <h3 className="font-ui text-body font-medium text-success-dark">
            项目"{project.name}"创建成功
          </h3>
          <p className="text-caption text-success-dark/80">
            数据源接入后, 系统会自动开始采集事件。首份周报草稿预计 24 小时内生成。
          </p>
        </div>
      </div>

      {addedDatasources.length > 0 ? (
        <div className="space-y-2">
          <p className="font-ui text-caption uppercase tracking-wider text-text-muted">
            已接入数据源 · {addedDatasources.length}
          </p>
          <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle bg-bg-card">
            {addedDatasources.map((ds) => (
              <li key={ds.id} className="flex items-center justify-between px-3 py-2">
                <span className="font-ui text-body-sm text-text-primary">
                  {TYPE_LABEL[ds.type] ?? ds.type}
                </span>
                <span className="font-mono text-caption text-text-subtle">{ds.name}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-caption text-text-subtle">
          没看到事件流? 检查插件是否运行 / PAT 是否有效。
        </p>
        <Button onClick={onGoToWorkbench} className="font-ui">
          进入工作台
          <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}
