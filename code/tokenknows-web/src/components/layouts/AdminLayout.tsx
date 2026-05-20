/**
 * AdminLayout · T15 实例管理员控制台。
 *
 * 设计依据: SharedFoundations.md §7.3
 * 深色 header (bg-inverse-bg) + sub-nav,视觉上与业务屏区分明显。
 */

import { Outlet, Link, useLocation, Navigate } from 'react-router-dom'
import { BarChart3, Users, Gauge, FileSearch, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'

const subNav = [
  { to: '/admin', icon: BarChart3, label: '统计' },
  { to: '/admin/users', icon: Users, label: '用户' },
  { to: '/admin/quotas', icon: Gauge, label: '配额' },
  { to: '/admin/audit', icon: FileSearch, label: '审计' },
]

export function AdminLayout() {
  const user = useAuthStore((s) => s.user)
  const location = useLocation()

  if (!user?.is_instance_admin) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="grid h-screen grid-rows-[56px_44px_1fr] bg-bg-page">
      {/* 深色 header */}
      <header className="flex items-center justify-between bg-inverse-bg px-6 text-inverse-text">
        <div className="flex items-center gap-3">
          <Link to="/admin" className="font-content text-h3">
            TokenKnows
          </Link>
          <span className="rounded-sm bg-inverse-accent px-1.5 py-0.5 font-ui text-micro font-medium text-inverse-text">
            实例管理
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-ui text-body-sm">{user.display_name}</span>
          <Link
            to="/"
            className="flex items-center gap-1 font-ui text-body-sm text-inverse-muted hover:text-inverse-text"
            title="返回业务区"
          >
            <LogOut className="size-3.5" />
            退出管理
          </Link>
        </div>
      </header>

      {/* Sub nav */}
      <nav
        className="flex items-center gap-1 border-b border-border-subtle bg-bg-card px-6"
        aria-label="管理子导航"
      >
        {subNav.map((item) => {
          const isActive = location.pathname === item.to
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 font-ui text-body-sm transition',
                isActive
                  ? 'border-b-2 border-text-primary text-text-primary'
                  : 'border-b-2 border-transparent text-text-muted hover:text-text-primary',
              )}
            >
              <item.icon className="size-3.5" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* 主区 */}
      <main className="overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
