/**
 * Step 2 · 数据源类型多选
 *
 * 决策 (TaskTechDesign T02):
 *   多选(GitHub + Claude Code 同时接);
 *   每张卡显示状态(待配置 / 已连接 / 失败,Step 2 阶段都是"待配置")。
 */

import { Code2, FileCode, Sparkles, Upload, Check } from 'lucide-react'
import { GithubIcon } from '@/components/icons/GithubIcon'
import { cn } from '@/lib/utils'
import type { DatasourceType } from '@/types/api'

interface StepDatasourcesProps {
  selectedTypes: DatasourceType[]
  onToggle: (ds: DatasourceType) => void
}

interface DatasourceCard {
  type: DatasourceType
  icon: React.ComponentType<{ className?: string }>
  title: string
  description: string
  recommended?: boolean
}

const cards: DatasourceCard[] = [
  {
    type: 'claude_code',
    icon: Sparkles,
    title: 'Claude Code',
    description: '插件捕获 AI 对话 / 工具调用 / 文件修改',
    recommended: true,
  },
  {
    type: 'github',
    icon: GithubIcon,
    title: 'GitHub',
    description: 'PAT 接入多仓库, 同步 PR / Issue / Commit',
    recommended: true,
  },
  {
    type: 'cursor',
    icon: Code2,
    title: 'Cursor',
    description: '扩展捕获 Chat + 文件 diff',
  },
  {
    type: 'vscode',
    icon: FileCode,
    title: 'VS Code',
    description: 'Copilot Chat + 文件修改捕获',
  },
  {
    type: 'local_file',
    icon: Upload,
    title: '本地文件',
    description: '上传 md / pdf / docx 补充语料',
  },
]

export function StepDatasources({ selectedTypes, onToggle }: StepDatasourcesProps) {
  return (
    <div className="space-y-3">
      <p className="text-body-sm text-text-muted">
        多选你的团队主要使用的工具。至少接入 1 个;后续可随时添加。
      </p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {cards.map((card) => {
          const Icon = card.icon
          const selected = selectedTypes.includes(card.type)
          return (
            <li key={card.type}>
              <button
                type="button"
                onClick={() => onToggle(card.type)}
                aria-pressed={selected}
                className={cn(
                  'group flex w-full items-start gap-3 rounded-lg border p-4 text-left transition',
                  selected
                    ? 'border-accent-primary bg-accent-primary-light shadow-elev-1'
                    : 'border-border-subtle bg-bg-card hover:border-border-medium hover:bg-bg-warm',
                )}
              >
                <Icon
                  className={cn(
                    'size-5 shrink-0 mt-0.5',
                    selected ? 'text-accent-primary-dark' : 'text-text-secondary',
                  )}
                />
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-ui text-body font-medium text-text-primary">
                      {card.title}
                    </h3>
                    {card.recommended && !selected ? (
                      <span className="rounded bg-warning-bg px-1.5 py-0.5 font-ui text-micro font-medium text-warning">
                        推荐
                      </span>
                    ) : null}
                  </div>
                  <p className="text-caption text-text-muted">{card.description}</p>
                </div>
                <div
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full transition',
                    selected
                      ? 'bg-accent-primary text-inverse-text'
                      : 'border border-border-medium bg-bg-card group-hover:border-text-subtle',
                  )}
                  aria-hidden="true"
                >
                  {selected ? <Check className="size-3" /> : null}
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
