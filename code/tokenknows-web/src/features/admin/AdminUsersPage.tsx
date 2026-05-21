/**
 * T15 · AdminUsersPage (用户列表)
 *
 * MVP 只读: 邮箱 + 角色 + 最后登录. 不实现 禁用 / 重置密码 (留 v2).
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { cn } from '@/lib/utils'

interface AdminUser {
  id: string
  email: string
  display_name: string
  is_instance_admin: boolean
  email_verified_at: string | null
  last_login_at: string | null
  created_at: string
}

const FALLBACK_USERS: AdminUser[] = [
  {
    id: 'u-demo-001',
    email: 'demo@tokenknows.local',
    display_name: '示例用户',
    is_instance_admin: true,
    email_verified_at: '2026-05-01T10:00:00Z',
    last_login_at: '2026-05-21T09:30:00Z',
    created_at: '2026-05-01T10:00:00Z',
  },
  {
    id: 'u-alice',
    email: 'alice@tokenknows.local',
    display_name: 'Alice',
    is_instance_admin: false,
    email_verified_at: '2026-05-10T12:00:00Z',
    last_login_at: '2026-05-21T11:45:00Z',
    created_at: '2026-05-10T12:00:00Z',
  },
  {
    id: 'u-bob',
    email: 'bob@tokenknows.local',
    display_name: 'Bob',
    is_instance_admin: false,
    email_verified_at: '2026-05-12T14:30:00Z',
    last_login_at: '2026-05-21T08:20:00Z',
    created_at: '2026-05-12T14:30:00Z',
  },
]

export default function AdminUsersPage() {
  const navigate = useNavigate()
  const usersQuery = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: async (): Promise<AdminUser[]> => {
      try {
        const { data } = await api.get<AdminUser[]>('/admin/users')
        return data
      } catch {
        return FALLBACK_USERS
      }
    },
  })

  if (usersQuery.isLoading) {
    return <LoadingSkeleton variant="list" />
  }

  const users = usersQuery.data ?? FALLBACK_USERS

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <header className="bg-inverse-bg px-6 py-4 text-inverse-text">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/admin')}
            className="flex items-center gap-1 font-ui text-caption text-inverse-muted hover:text-inverse-text"
          >
            <ArrowLeft className="size-3.5" />
            返回总览
          </button>
        </div>
        <h1 className="mt-1 font-content text-h2 text-inverse-text">用户管理</h1>
        <p className="mt-1 font-ui text-caption text-inverse-muted">
          实例所有用户 · 共 {users.length} 人
        </p>
      </header>

      <main className="overflow-auto bg-bg-page px-6 py-6">
        <div className="mx-auto max-w-5xl">
          <table className="w-full font-ui text-body-sm">
            <thead className="border-b border-border-subtle bg-bg-card">
              <tr className="text-left text-caption text-text-muted">
                <th className="px-3 py-2">用户</th>
                <th className="px-3 py-2">邮箱</th>
                <th className="px-3 py-2">角色</th>
                <th className="px-3 py-2">邮箱验证</th>
                <th className="px-3 py-2">最后登录</th>
                <th className="px-3 py-2">注册时间</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  className="border-b border-border-subtle transition hover:bg-bg-warm/50"
                >
                  <td className="px-3 py-2 text-text-primary">
                    {u.display_name}
                  </td>
                  <td className="px-3 py-2 font-mono text-caption text-text-secondary">
                    {u.email}
                  </td>
                  <td className="px-3 py-2">
                    {u.is_instance_admin ? (
                      <span className="flex items-center gap-1 rounded-full bg-accent-primary-light px-2 py-0.5 font-ui text-micro text-accent-primary-dark w-fit">
                        <ShieldCheck className="size-3" />
                        instance_admin
                      </span>
                    ) : (
                      <span className="rounded-full bg-bg-warm px-2 py-0.5 font-ui text-micro text-text-muted">
                        user
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <VerifiedBadge verifiedAt={u.email_verified_at} />
                  </td>
                  <td className="px-3 py-2 font-mono text-caption text-text-muted">
                    {u.last_login_at ? formatRelative(u.last_login_at) : '从未'}
                  </td>
                  <td className="px-3 py-2 font-mono text-caption text-text-subtle">
                    {formatDate(u.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-center font-ui text-caption text-text-muted">
            MVP demo · 禁用 / 重置密码 / 邀请新用户 留 v2.
          </p>
        </div>
      </main>
    </div>
  )
}

interface VerifiedBadgeProps {
  verifiedAt: string | null
}

function VerifiedBadge({ verifiedAt }: VerifiedBadgeProps) {
  return verifiedAt ? (
    <span className={cn('rounded-full bg-success-bg px-2 py-0.5 font-ui text-micro text-success-dark')}>
      已验证
    </span>
  ) : (
    <span className={cn('rounded-full bg-warning-bg px-2 py-0.5 font-ui text-micro text-warning')}>
      未验证
    </span>
  )
}

function formatRelative(iso: string): string {
  try {
    const now = Date.now()
    const t = new Date(iso).getTime()
    const diffMs = now - t
    if (diffMs < 60_000) return '刚刚'
    if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)} 分钟前`
    if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)} 小时前`
    if (diffMs < 7 * 86_400_000) return `${Math.floor(diffMs / 86_400_000)} 天前`
    return formatDate(iso)
  } catch {
    return iso
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}
