/**
 * PasswordInput · 密码输入 + 眼睛切换显示。
 *
 * 包装 shadcn Input,加右侧切换按钮。通过 ref 转发,与 react-hook-form register() 兼容。
 */

import { forwardRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface PasswordInputProps extends Omit<React.ComponentProps<typeof Input>, 'type'> {
  showLabel?: string
  hideLabel?: string
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  function PasswordInput(
    { className, showLabel = '显示密码', hideLabel = '隐藏密码', ...rest },
    ref,
  ) {
    const [visible, setVisible] = useState(false)
    return (
      <div className="relative">
        <Input
          ref={ref}
          type={visible ? 'text' : 'password'}
          className={cn('pr-10', className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? hideLabel : showLabel}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text-muted transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
    )
  },
)
