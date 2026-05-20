/**
 * PluginConnector · Claude Code / Cursor / VS Code 通用接入卡。
 *
 * 流程:
 *   未连接 → 点"生成连接 token" → POST /datasources/:type → 返回 token
 *   → 显示 TokenDisplay + 安装指南。
 */

import { Sparkles, Code2, FileCode, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConnectorCard } from './ConnectorCard'
import { TokenDisplay } from './TokenDisplay'
import type { Datasource, DatasourceType } from '@/types/api'

type PluginType = Extract<DatasourceType, 'claude_code' | 'cursor' | 'vscode'>

interface PluginMeta {
  icon: React.ComponentType<{ className?: string }>
  title: string
  installCommand: string
  docUrl: string
}

const META: Record<PluginType, PluginMeta> = {
  claude_code: {
    icon: Sparkles,
    title: 'Claude Code',
    installCommand: 'claude plugin install tokenknows-collector',
    docUrl: 'https://docs.tokenknows.local/connectors/claude-code',
  },
  cursor: {
    icon: Code2,
    title: 'Cursor 扩展',
    installCommand: 'Cursor → Extensions → 搜索 "TokenKnows Collector"',
    docUrl: 'https://docs.tokenknows.local/connectors/cursor',
  },
  vscode: {
    icon: FileCode,
    title: 'VS Code 扩展',
    installCommand: 'code --install-extension tokenknows.collector',
    docUrl: 'https://docs.tokenknows.local/connectors/vscode',
  },
}

interface PluginConnectorProps {
  type: PluginType
  datasource?: Datasource
  isPending: boolean
  onCreate: () => void
}

export function PluginConnector({ type, datasource, isPending, onCreate }: PluginConnectorProps) {
  const meta = META[type]
  const connected = Boolean(datasource?.connection_token)
  const state = connected ? 'connected' : isPending ? 'in_progress' : 'pending'

  return (
    <ConnectorCard icon={meta.icon} title={meta.title} state={state}>
      {connected && datasource?.connection_token ? (
        <div className="space-y-3">
          <ol className="list-decimal space-y-1 pl-5 font-ui text-caption text-text-secondary">
            <li>本机安装插件:</li>
          </ol>
          <code className="block rounded bg-inverse-bg px-3 py-2 font-mono text-caption text-inverse-text">
            {meta.installCommand}
          </code>
          <TokenDisplay token={datasource.connection_token} />
          <a
            href={meta.docUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-ui text-caption text-accent-primary-dark hover:underline"
          >
            完整文档 →
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-caption text-text-muted">
            点击下方按钮生成专属连接 token, 粘贴到本机插件即可开始采集。
          </p>
          <Button
            type="button"
            variant="secondary"
            className="font-ui"
            disabled={isPending}
            onClick={onCreate}
          >
            {isPending ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                生成中...
              </>
            ) : (
              '生成连接 token'
            )}
          </Button>
        </div>
      )}
    </ConnectorCard>
  )
}
