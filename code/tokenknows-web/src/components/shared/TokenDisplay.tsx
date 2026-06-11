/**
 * TokenDisplay · 连接 token 显示 + 显示切换 + 复制 + toast。
 *
 * 决策 (TaskTechDesign T02): token 默认遮蔽 + "显示"按钮 + 复制 toast。
 *
 * Phase B: 从 features/projects/components/connectors/ 移到 shared,
 * 供连接器 + MCP 接入 (个人 API token) 共用。遮蔽逻辑同步修复:
 * 不再只匹配 JWT 点分格式, 任意 token 都遮蔽尾部。
 */

import { useState } from 'react'
import { Eye, EyeOff, Copy, Check } from 'lucide-react'

interface TokenDisplayProps {
  token: string
  label?: string
  helpText?: string
}

export function TokenDisplay({
  token,
  label = '连接 token',
  helpText = '粘贴到插件 / 扩展配置中。token 长期有效, 可在项目设置里随时重置。',
}: TokenDisplayProps) {
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)

  const masked =
    token.length > 16 ? token.slice(0, 12) + '•'.repeat(16) : '•'.repeat(16)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // 老浏览器 fallback
      const ta = document.createElement('textarea')
      ta.value = token
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } finally {
        document.body.removeChild(ta)
      }
    }
  }

  return (
    <div className="space-y-1.5">
      <label className="font-ui text-caption text-text-secondary">{label}</label>
      <div className="flex items-stretch gap-1.5">
        <code className="flex-1 truncate rounded-md border border-border-subtle bg-bg-page px-3 py-2 font-mono text-body-sm text-text-primary">
          {visible ? token : masked}
        </code>
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? '隐藏 token' : '显示 token'}
          className="rounded-md border border-border-subtle bg-bg-card px-2 text-text-muted transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
        <button
          type="button"
          onClick={handleCopy}
          aria-label="复制 token"
          className="flex items-center gap-1 rounded-md border border-border-subtle bg-bg-card px-2.5 font-ui text-caption text-text-secondary transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        >
          {copied ? (
            <>
              <Check className="size-3.5 text-success" />
              已复制
            </>
          ) : (
            <>
              <Copy className="size-3.5" />
              复制
            </>
          )}
        </button>
      </div>
      <p className="text-caption text-text-subtle">{helpText}</p>
    </div>
  )
}
