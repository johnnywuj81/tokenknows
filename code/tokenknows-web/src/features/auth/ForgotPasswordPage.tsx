/**
 * T01 · ForgotPasswordPage
 *
 * 单 email 字段,提交后展示"邮件已发送"(防枚举:无论邮箱是否存在都展示相同提示)。
 */

import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Mail } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { AuthCard } from './components/AuthCard'
import { useForgotPassword } from './hooks/useForgotPassword'
import { isApiError } from '@/lib/api'

const schema = z.object({
  email: z.string().email('请输入有效邮箱'),
})

type FormData = z.infer<typeof schema>

export default function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { email: '' },
  })

  const onSubmit = (form: FormData) => forgot.mutate(form.email)

  // 成功态 · 不区分邮箱是否存在(防枚举)
  if (forgot.isSuccess) {
    return (
      <AuthCard
        title="检查你的邮箱"
        description="如果该邮箱存在,我们已发送重置密码的链接。链接有效期 1 小时。"
        footer={
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            返回登录
          </Link>
        }
      >
        <div className="flex items-start gap-3 rounded-md border border-success-border bg-success-bg px-4 py-3 text-success-dark">
          <Mail className="size-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-ui text-body-sm font-medium">邮件已发送</p>
            <p className="text-caption text-text-muted">
              没收到? 检查垃圾邮件,或几分钟后重试。
            </p>
          </div>
        </div>
      </AuthCard>
    )
  }

  const errorMessage = isApiError(forgot.error) ? forgot.error.message : null

  return (
    <AuthCard
      title="找回密码"
      description="输入注册邮箱,我们将发送重置链接给你。"
      footer={
        <span>
          想起来了?{' '}
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            返回登录
          </Link>
        </span>
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

        {errorMessage ? (
          <div
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </div>
        ) : null}

        <Button type="submit" className="w-full font-ui" disabled={forgot.isPending}>
          {forgot.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              发送中...
            </>
          ) : (
            '发送重置链接'
          )}
        </Button>
      </form>
    </AuthCard>
  )
}
