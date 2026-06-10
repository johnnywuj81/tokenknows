/**
 * ErrorState · 错误展示 + 重试按钮。
 *
 * 设计依据: SharedFoundations.md §3.3
 *
 * 用法:
 *   const { data, error, refetch } = useQuery(...)
 *   if (error) return <ErrorState error={error} onRetry={() => refetch()} />
 */

import type { ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { isApiError } from '@/lib/api'

interface ErrorStateProps {
  title?: string
  /** 无 error 对象时的补充说明文案 (有 error 时优先显示 error message) */
  description?: string
  error?: unknown
  onRetry?: () => void
  variant?: 'inline' | 'fullscreen'
  className?: string
  action?: ReactNode    // 自定义附加操作
}

function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (isApiError(error)) return error.message
  if (error instanceof Error) return error.message
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message)
  }
  return '未知错误'
}

export function ErrorState({
  title = '加载失败',
  description,
  error,
  onRetry,
  variant = 'inline',
  className,
  action,
}: ErrorStateProps) {
  const message = error ? getErrorMessage(error) : description
  const isFullscreen = variant === 'fullscreen'

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 text-center',
        isFullscreen ? 'min-h-[60vh] p-8' : 'p-6',
        className,
      )}
      role="alert"
    >
      <AlertTriangle className="size-10 text-danger" aria-hidden="true" />
      <h3 className="font-content text-h3 text-text-primary">{title}</h3>
      {message ? (
        <p className="text-body-sm text-text-muted max-w-md break-words">{message}</p>
      ) : null}
      <div className="mt-2 flex items-center gap-2">
        {onRetry ? (
          <Button
            variant="outline"
            onClick={onRetry}
            className="font-ui"
          >
            <RefreshCw className="size-3.5" />
            重试
          </Button>
        ) : null}
        {action}
      </div>
    </div>
  )
}
