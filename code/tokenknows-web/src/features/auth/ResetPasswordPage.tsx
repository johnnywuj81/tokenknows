/**
 * T01 · ResetPasswordPage
 *
 * URL ?token=xxx + 新密码二次确认。
 * 成功 → 跳 /login。
 *
 * 关键决策 (TaskTechDesign T01):
 *   token 失效要展示具体错误。
 */

import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, AlertTriangle } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { AuthCard } from './components/AuthCard'
import { PasswordInput } from './components/PasswordInput'
import { useResetPassword } from './hooks/useResetPassword'
import { isApiError } from '@/lib/api'

const schema = z
  .object({
    new_password: z
      .string()
      .min(10, '密码至少 10 位')
      .refine((v) => /[a-zA-Z]/.test(v), '需包含字母')
      .refine((v) => /\d/.test(v), '需包含数字')
      .refine((v) => /[^a-zA-Z0-9]/.test(v), '需包含符号'),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, {
    message: '两次输入不一致',
    path: ['confirm'],
  })

type FormData = z.infer<typeof schema>

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const navigate = useNavigate()
  const reset = useResetPassword()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { new_password: '', confirm: '' },
  })

  // 成功 → 1.5s 后跳 /login
  useEffect(() => {
    if (reset.isSuccess) {
      const id = setTimeout(() => navigate('/login', { replace: true }), 1500)
      return () => clearTimeout(id)
    }
  }, [reset.isSuccess, navigate])

  // 无 token
  if (!token) {
    return (
      <AuthCard
        title="链接无效"
        description="缺少 token,无法重置密码。"
        footer={
          <Link to="/forgot-password" className="text-accent-primary-dark hover:underline">
            重新发送邮件
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

  const onSubmit = (form: FormData) =>
    reset.mutate({ token, new_password: form.new_password })

  if (reset.isSuccess) {
    return (
      <AuthCard
        title="密码已重置"
        description="即将跳转到登录页..."
      >
        <div className="flex items-center gap-3 rounded-md border border-success-border bg-success-bg px-4 py-3 text-success-dark">
          <Loader2 className="size-5 shrink-0 animate-spin" />
          <p className="text-body-sm">使用新密码登录</p>
        </div>
      </AuthCard>
    )
  }

  const apiErr = isApiError(reset.error) ? reset.error : null
  const errorMessage = apiErr?.message ?? null

  return (
    <AuthCard
      title="设置新密码"
      description="设置后请使用新密码登录。"
      footer={
        <Link to="/login" className="text-text-muted hover:text-text-primary">
          返回登录
        </Link>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="new_password">新密码</Label>
          <PasswordInput
            id="new_password"
            autoComplete="new-password"
            placeholder="至少 10 位,含字母+数字+符号"
            aria-invalid={Boolean(errors.new_password)}
            {...register('new_password')}
          />
          {errors.new_password ? (
            <p className="text-caption text-danger" role="alert">
              {errors.new_password.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="confirm">再次输入</Label>
          <PasswordInput
            id="confirm"
            autoComplete="new-password"
            placeholder="再输一遍"
            aria-invalid={Boolean(errors.confirm)}
            {...register('confirm')}
          />
          {errors.confirm ? (
            <p className="text-caption text-danger" role="alert">
              {errors.confirm.message}
            </p>
          ) : null}
        </div>

        {errorMessage ? (
          <div
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
            role="alert"
          >
            <p>{errorMessage}</p>
            {apiErr ? (
              <p className="mt-1 text-caption text-text-muted">错误码 · {apiErr.code}</p>
            ) : null}
          </div>
        ) : null}

        <Button type="submit" className="w-full font-ui" disabled={reset.isPending}>
          {reset.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              提交中...
            </>
          ) : (
            '重置密码'
          )}
        </Button>
      </form>
    </AuthCard>
  )
}
