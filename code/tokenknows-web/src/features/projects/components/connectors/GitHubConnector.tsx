/**
 * GitHubConnector · PAT + 仓库接入。
 *
 * 验证: PAT 必须以 ghp_ 开头(mock 校验, 真后端会校验 scopes)。
 */

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { GithubIcon } from '@/components/icons/GithubIcon'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { ConnectorCard } from './ConnectorCard'
import type { Datasource } from '@/types/api'
import { isApiError } from '@/lib/api'

interface GitHubConnectorProps {
  datasource?: Datasource
  isPending: boolean
  error: unknown
  onSubmit: (input: { pat: string; repos: string[] }) => void
}

export function GitHubConnector({ datasource, isPending, error, onSubmit }: GitHubConnectorProps) {
  const [pat, setPat] = useState('')
  const [reposText, setReposText] = useState('')

  const connected = Boolean(datasource)
  const state = connected ? 'connected' : isPending ? 'in_progress' : 'pending'
  const errorMessage = isApiError(error) ? error.message : null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const repos = reposText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
    onSubmit({ pat: pat.trim(), repos })
  }

  return (
    <ConnectorCard icon={GithubIcon} title="GitHub" state={state}>
      {connected ? (
        <div className="space-y-2">
          <p className="text-caption text-text-secondary">
            已接入 <strong>{Array.isArray(datasource?.config?.repos) ? (datasource?.config?.repos as string[]).length : 0}</strong> 个仓库。
          </p>
          <p className="text-caption text-text-subtle">
            首次全量同步默认抓最近 90 天数据;之后 webhook + 轮询保持增量。
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="github_pat">
              Personal Access Token <span className="text-danger">*</span>
            </Label>
            <Input
              id="github_pat"
              type="password"
              value={pat}
              onChange={(e) => setPat(e.target.value)}
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
              autoComplete="off"
              spellCheck={false}
              required
            />
            <p className="text-caption text-text-subtle">
              至少需要 <code className="font-mono">repo:read</code> /{' '}
              <code className="font-mono">pull_requests:read</code> /{' '}
              <code className="font-mono">issues:read</code>。
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="github_repos">仓库(每行一个,owner/repo 格式)</Label>
            <Textarea
              id="github_repos"
              value={reposText}
              onChange={(e) => setReposText(e.target.value)}
              placeholder={'TokenKnows/api\nTokenKnows/web'}
              rows={3}
            />
          </div>

          {errorMessage ? (
            <div
              className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
              role="alert"
            >
              {errorMessage}
            </div>
          ) : null}

          <Button type="submit" disabled={isPending || !pat.trim()} className="font-ui">
            {isPending ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                校验中...
              </>
            ) : (
              '校验并接入'
            )}
          </Button>
        </form>
      )}
    </ConnectorCard>
  )
}
