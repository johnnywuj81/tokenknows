/**
 * RouteErrorBoundary · v2.1 T124
 *
 * react-router 路由级错误边界. 任何路由 component 抛 uncaught error 时:
 *   1. 不显示 react-router 默认 'Unexpected Application Error!' 黑屏
 *   2. 显示带 "重试 / 返回首页 / 复制错误" 操作的友好卡
 *   3. dev mode 显示完整 stack; prod 隐藏
 *
 * 用法: 在 routes/index.tsx 给每个 route 加 errorElement={<RouteErrorBoundary />}
 */

import { useRouteError, useNavigate, Link, isRouteErrorResponse } from 'react-router-dom'
import { AlertTriangle, RotateCcw, Home, Copy } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function RouteErrorBoundary() {
  const error = useRouteError()
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  let title = '页面崩溃'
  let detail = ''
  let stack = ''

  if (isRouteErrorResponse(error)) {
    title = `HTTP ${error.status}${error.statusText ? ' · ' + error.statusText : ''}`
    detail = typeof error.data === 'string' ? error.data : JSON.stringify(error.data)
  } else if (error instanceof Error) {
    detail = error.message
    stack = error.stack ?? ''
  } else {
    detail = String(error)
  }

  function handleRetry() {
    // 强刷当前 URL
    navigate(0)
  }

  async function handleCopy() {
    const text = `[${title}]\n${detail}\n\n${stack}`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* 静默 */
    }
  }

  const isDev = import.meta.env.DEV

  return (
    <div
      className="flex h-full min-h-[60vh] items-center justify-center p-6"
      data-testid="route-error-boundary"
      role="alert"
    >
      <div className="w-full max-w-2xl rounded-lg border border-danger-border bg-bg-card p-6 shadow-elev-1">
        <div className="flex items-start gap-3">
          <AlertTriangle className="size-6 shrink-0 text-danger" />
          <div className="flex-1 min-w-0">
            <h1 className="font-content text-h2 text-text-primary">{title}</h1>
            <p className="mt-1 font-ui text-body-sm text-text-secondary break-words">
              {detail || '页面渲染出错, 通常刷新或返回上一页能恢复.'}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={handleRetry} size="sm" className="font-ui">
            <RotateCcw className="size-3.5" />
            重试
          </Button>
          <Button asChild variant="outline" size="sm" className="font-ui">
            <Link to="/">
              <Home className="size-3.5" />
              返回工作台
            </Link>
          </Button>
          <Button
            onClick={handleCopy}
            variant="ghost"
            size="sm"
            className="font-ui"
            disabled={copied}
          >
            <Copy className="size-3.5" />
            {copied ? '已复制' : '复制错误信息'}
          </Button>
        </div>

        {isDev && stack ? (
          <details
            className={cn(
              'mt-4 rounded-md border border-border-subtle bg-bg-warm p-3',
            )}
          >
            <summary className="cursor-pointer font-ui text-caption font-medium text-text-secondary">
              开发模式 · stack trace
            </summary>
            <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all font-mono text-micro text-text-muted">
              {stack}
            </pre>
          </details>
        ) : null}

        <p className="mt-4 font-ui text-caption text-text-subtle">
          这个错误不会丢失你已保存的内容. 如果反复出现, 把错误信息发给管理员 / 提 issue.
        </p>
      </div>
    </div>
  )
}
