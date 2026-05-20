/**
 * T01 · RegisterPage
 *
 * 关键决策 (TaskTechDesign T01):
 *   注册成功不自动登录,跳"请检查邮箱"中间态。
 *   状态机: form (默认) → pending (已提交,等待验证邮件)。
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Mail, CheckCircle2 } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useRegister } from './hooks/useRegister'
import { AuthCard } from './components/AuthCard'
import { PasswordInput } from './components/PasswordInput'
import { isApiError } from '@/lib/api'

const schema = z.object({
  email: z.string().email('请输入有效邮箱'),
  display_name: z.string().trim().min(2, '昵称至少 2 个字符').max(40, '昵称过长'),
  password: z
    .string()
    .min(10, '密码至少 10 位')
    .refine((v) => /[a-zA-Z]/.test(v), '需包含字母')
    .refine((v) => /\d/.test(v), '需包含数字')
    .refine((v) => /[^a-zA-Z0-9]/.test(v), '需包含符号 (PRD §6.2)'),
})

type FormData = z.infer<typeof schema>

export default function RegisterPage() {
  const reg = useRegister()
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', display_name: '', password: '' },
  })

  const onSubmit = (form: FormData) => {
    reg.mutate(form, {
      onSuccess: () => setSubmittedEmail(form.email),
    })
  }

  // 状态 2 · 提交成功 → 请检查邮箱
  if (submittedEmail) {
    return (
      <AuthCard
        title="请检查邮箱"
        description={
          <>
            我们已向 <strong className="text-text-primary">{submittedEmail}</strong> 发送了验证邮件,
            请点击邮件中的链接完成验证。
          </>
        }
        footer={
          <div className="flex items-center justify-between">
            <span>
              没收到?{' '}
              <button
                type="button"
                onClick={() => reg.mutate({ email: submittedEmail, display_name: '', password: '' })}
                className="text-accent-primary-dark hover:underline"
                disabled={reg.isPending}
              >
                重新发送
              </button>
            </span>
            <Link to="/login" className="text-text-muted hover:text-text-primary">
              返回登录
            </Link>
          </div>
        }
      >
        <div className="flex items-center gap-3 rounded-md border border-success-border bg-success-bg px-4 py-3 text-success-dark">
          <CheckCircle2 className="size-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-ui text-body-sm font-medium">注册成功,等待邮箱验证</p>
            <p className="text-caption text-text-muted">
              邮件有效期 24 小时。验证后即可登录。
            </p>
          </div>
        </div>
        <p className="mt-4 flex items-center gap-2 text-caption text-text-subtle">
          <Mail className="size-3.5" />
          看不到邮件? 检查垃圾邮件或联系实例管理员。
        </p>
      </AuthCard>
    )
  }

  // 状态 1 · 表单
  const errorMessage = reg.error && isApiError(reg.error) ? reg.error.message : null

  return (
    <AuthCard
      title="创建账号"
      description="加入团队的私有化研发知识平台"
      footer={
        <span>
          已有账号?{' '}
          <Link to="/login" className="text-accent-primary-dark hover:underline">
            登录
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

        <div className="space-y-1.5">
          <Label htmlFor="display_name">昵称</Label>
          <Input
            id="display_name"
            autoComplete="name"
            placeholder="同事看到的名字"
            aria-invalid={Boolean(errors.display_name)}
            {...register('display_name')}
          />
          {errors.display_name ? (
            <p className="text-caption text-danger" role="alert">
              {errors.display_name.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">密码</Label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            placeholder="至少 10 位,含字母+数字+符号"
            aria-invalid={Boolean(errors.password)}
            {...register('password')}
          />
          {errors.password ? (
            <p className="text-caption text-danger" role="alert">
              {errors.password.message}
            </p>
          ) : (
            <p className="text-caption text-text-subtle">
              至少 10 位,含字母+数字+符号
            </p>
          )}
        </div>

        {errorMessage ? (
          <div
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-body-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </div>
        ) : null}

        <Button type="submit" className="w-full font-ui" disabled={reg.isPending}>
          {reg.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              注册中...
            </>
          ) : (
            '注册'
          )}
        </Button>
      </form>
    </AuthCard>
  )
}
