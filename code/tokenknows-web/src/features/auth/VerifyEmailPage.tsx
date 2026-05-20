/**
 * T01 · VerifyEmailPage
 *
 * URL ?token=xxx 在挂载时自动 POST 验证。
 * 状态机: pending (验证中) → success / error。
 *
 * 关键决策 (TaskTechDesign T01):
 *   token 失效要展示具体错误,不要笼统"失败"。
 *   `/verify-email` 的 token 在 URL query, page mount 时直接 POST,不要等用户点按钮。
 */

import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, AlertTriangle } from 'lucide-react'
import { AuthCard } from './components/AuthCard'
import { useVerifyEmail } from './hooks/useVerifyEmail'
import { isApiError } from '@/lib/api'

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const verify = useVerifyEmail()

  // 严格避免 StrictMode 下挂载 effect 跑两次重复请求
  const triggered = useRef(false)
  useEffect(() => {
    if (!token || triggered.current) return
    triggered.current = true
    verify.mutate(token)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 故意只在首挂载触发
  }, [token])

  // 无 token
  if (!token) {
    return (
      <AuthCard
        title="链接无效"
        description="缺少验证 token。如果你是从邮件中点过来的,请检查链接是否完整。"
        footer={
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            返回登录
          </Link>
        }
      >
        <div className="flex items-center gap-3 rounded-md border border-danger-border bg-danger-bg px-4 py-3 text-danger">
          <AlertTriangle className="size-5 shrink-0" />
          <p className="text-body-sm">URL 中没有 ?token= 参数</p>
        </div>
      </AuthCard>
    )
  }

  // pending
  if (verify.isPending || verify.isIdle) {
    return (
      <AuthCard title="正在验证..." description="请稍候,我们正在核对你的邮箱。">
        <div className="flex items-center gap-3 rounded-md border border-border-subtle bg-bg-card px-4 py-6 text-text-muted">
          <Loader2 className="size-5 animate-spin" />
          <p className="text-body-sm">验证 token 中</p>
        </div>
      </AuthCard>
    )
  }

  // success
  if (verify.isSuccess) {
    return (
      <AuthCard
        title="邮箱已验证"
        description="你的账号已激活,现在可以登录使用了。"
        footer={
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            前往登录
          </Link>
        }
      >
        <div className="flex items-center gap-3 rounded-md border border-success-border bg-success-bg px-4 py-3 text-success-dark">
          <CheckCircle2 className="size-5 shrink-0" />
          <p className="text-body-sm">验证成功</p>
        </div>
      </AuthCard>
    )
  }

  // error - 具体错误展示
  const apiErr = isApiError(verify.error) ? verify.error : null
  const specificMessage = apiErr?.message ?? '验证过程中发生错误'

  return (
    <AuthCard
      title="验证失败"
      description="可能的原因: token 已使用 / token 已过期 / 链接被截断。"
      footer={
        <div className="flex items-center justify-between">
          <Link to="/register" className="text-text-muted hover:text-text-primary">
            重新注册
          </Link>
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            尝试登录
          </Link>
        </div>
      }
    >
      <div className="flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg px-4 py-3 text-danger">
        <AlertTriangle className="size-5 shrink-0" />
        <div className="space-y-1">
          <p className="font-ui text-body-sm font-medium">{specificMessage}</p>
          {apiErr ? (
            <p className="text-caption text-text-muted">错误码 · {apiErr.code}</p>
          ) : null}
        </div>
      </div>
    </AuthCard>
  )
}
