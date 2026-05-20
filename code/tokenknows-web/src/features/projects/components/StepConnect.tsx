/**
 * Step 3 · 接入指引(每个 selected 数据源一张卡)
 *
 * 决策 (TaskTechDesign T02):
 *   - 每个数据源**独立卡片**, 不并排挤一屏(垂直堆叠);
 *   - 连接 token 默认遮蔽 + "显示"按钮 + 复制 toast(TokenDisplay 实现);
 *   - GitHub PAT 校验 ghp_ 前缀(后端 mock 校验)。
 */

import { useState } from 'react'
import type { Datasource, DatasourceType, Project } from '@/types/api'
import { useAddDatasource } from '../hooks/useAddDatasource'
import { PluginConnector } from './connectors/PluginConnector'
import { GitHubConnector } from './connectors/GitHubConnector'
import { LocalFileConnector } from './connectors/LocalFileConnector'

interface StepConnectProps {
  project: Project
  selectedTypes: DatasourceType[]
  addedDatasources: Datasource[]
  onDatasourceAdded: (ds: Datasource) => void
}

export function StepConnect({
  project,
  selectedTypes,
  addedDatasources,
  onDatasourceAdded,
}: StepConnectProps) {
  const addDs = useAddDatasource()
  const [activeType, setActiveType] = useState<DatasourceType | null>(null)

  const handleCreate = (type: DatasourceType, body?: { pat?: string; repos?: string[] }) => {
    setActiveType(type)
    addDs.mutate(
      { projectId: project.id, type, body },
      {
        onSuccess: (ds) => {
          onDatasourceAdded(ds)
          setActiveType(null)
        },
        onError: () => setActiveType(null),
      },
    )
  }

  const findAdded = (type: DatasourceType): Datasource | undefined =>
    addedDatasources.find((d) => d.type === type)

  return (
    <div className="space-y-4">
      <p className="text-body-sm text-text-muted">
        至少完成 <strong className="text-text-primary">1 个</strong> 数据源接入即可进入下一步。其他可以稍后补。
      </p>
      <div className="space-y-3">
        {selectedTypes.map((type) => {
          const isPending = addDs.isPending && activeType === type
          const ds = findAdded(type)
          if (type === 'claude_code' || type === 'cursor' || type === 'vscode') {
            return (
              <PluginConnector
                key={type}
                type={type}
                datasource={ds}
                isPending={isPending}
                onCreate={() => handleCreate(type)}
              />
            )
          }
          if (type === 'github') {
            return (
              <GitHubConnector
                key={type}
                datasource={ds}
                isPending={isPending}
                error={isPending ? null : addDs.error}
                onSubmit={(input) => handleCreate('github', input)}
              />
            )
          }
          if (type === 'local_file') {
            return (
              <LocalFileConnector
                key={type}
                onSkip={() => {
                  /* no-op, 用户继续 */
                }}
              />
            )
          }
          return null
        })}
      </div>
    </div>
  )
}
