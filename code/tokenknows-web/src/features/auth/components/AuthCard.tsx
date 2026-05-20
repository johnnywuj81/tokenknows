/**
 * AuthCard · T01 表单容器 (注册/登录/找回/重置共用)。
 *
 * 视觉: 顶部品牌头 (logo + title) + 描述行 + slot body + 底部链接 slot。
 * 不带阴影/边框 - AuthLayout 右侧已是卡片化布局。
 */

import type { ReactNode } from 'react'

interface AuthCardProps {
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode      // 切换链接 (e.g. "已有账号?登录")
}

export function AuthCard({ title, description, children, footer }: AuthCardProps) {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          TokenKnows
        </p>
        <h1 className="font-content text-h1 text-text-primary">{title}</h1>
        {description ? (
          <p className="text-body text-text-muted">{description}</p>
        ) : null}
      </header>

      <div>{children}</div>

      {footer ? (
        <footer className="text-body-sm text-text-muted">{footer}</footer>
      ) : null}
    </div>
  )
}
