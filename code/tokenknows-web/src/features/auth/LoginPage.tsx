/**
 * T01 · LoginPage
 *
 * 设计依据:
 *   - tasks/T01-auth.md §4-§9
 *   - SharedFoundations.md §3 (Error 归一) / §4.1 (authStore)
 *   - TaskTechDesign.md Part 2 T01 关键决策
 */

import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { useLogin } from './hooks/useLogin'
import { AuthCard } from './components/AuthCard'
import { PasswordInput } from './components/PasswordInput'
import { isApiError } from '@/lib/api'

const schema = z.object({
  email: z.string().email('请输入有效邮箱'),
  password: z.string().min(1, '请输入密码'),
})

type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const login = useLogin()

  // 423 lock 倒计时 (mock 不会触发,但代码就位)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const [remainSec, setRemainSec] = useState(0)
  useEffect(() => {
    if (!lockedUntil) return
    const tick = () => {
      const remain = Math.max(0, Math.ceil((lockedUntil - Date.now()) / 1000))
      setRemainSec(remain)
      if (remain <= 0) setLockedUntil(null)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [lockedUntil])

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  // 已登录访问 /login → 跳 redirect 或 /
  if (isAuthenticated) {
    const redirect = searchParams.get('redirect') ?? '/'
    return <Navigate to={redirect} replace />
  }

  const onSubmit = (form: FormData) => {
    setLockedUntil(null)
    login.mutate(form, {
      onSuccess: () => {
        const redirect = searchParams.get('redirect') ?? '/'
        navigate(redirect, { replace: true })
      },
      onError: (err) => {
        // 423 → 进入倒计时
        if (isApiError(err) && err.status === 423) {
          // 后端约定 detail.locked_until_seconds; mock 不会触发
          const seconds =
            (err.detail as { locked_until_seconds?: number } | undefined)?.locked_until_seconds ?? 15 * 60
          setLockedUntil(Date.now() + seconds * 1000)
        }
      },
    })
  }

  const errorMessage = login.error && isApiError(login.error) ? login.error.message : null
  const isLocked = lockedUntil !== null && remainSec > 0

  return (
    <AuthCard
      title="欢迎回来"
      description="登录以继续访问你的研发知识资产"
      footer={
        <div className="flex items-center justify-between">
          <span>
            还没有账号?{' '}
            <Link to="/register" className="text-accent-primary-dark hover:underline">
              注册
            </Link>
          </span>
          <Link to="/forgot-password" className="text-text-muted hover:text-text-primary">
            忘记密码?
          </Link>
        </div>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">邮箱</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            aria-invalid={Boolean(errors.email)}
            {...register('email')}
          />
          {errors.email ? (
            <p className="text-caption text-danger" role="alert">
              {errors.email.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">密码</Label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder="请输入密码"
            aria-invalid={Boolean(errors.password)}
            {...register('password')}
          />
          {errors.password ? (
            <p className="text-caption text-danger" role="alert">
              {errors.password.message}
            </p>
          ) : null}
        </div>

        {/* 后端错误 banner (zod 错误已经行级显示) */}
        {errorMessage && !isLocked ? (
          <div
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </div>
        ) : null}

        {/* 423 lock 倒计时 */}
        {isLocked ? (
          <div
            className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-body-sm text-warning"
            role="alert"
          >
            账号已被临时锁定,请 {Math.floor(remainSec / 60)} 分 {remainSec % 60} 秒后重试
          </div>
        ) : null}

        <Button
          type="submit"
          className="w-full font-ui"
          disabled={login.isPending || isLocked}
        >
          {login.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              登录中...
            </>
          ) : (
            '登录'
          )}
        </Button>
      </form>
    </AuthCard>
  )
}
