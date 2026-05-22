/**
 * AppLayout · 主业务屏 shell(T02-T13)。
 *
 * 设计依据: SharedFoundations.md §7.3
 * 顶栏 + 左侧导航 + 主区 + 抽屉槽位(React Portal target)
 *
 * 顶栏内容(实例信息 + 项目选择 + 用户)在 T03 完整实现,
 * 这里只搭骨架,文字占位。
 */

import { Outlet, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, FileText, Sparkles, Plug, Settings, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { useProjectStore } from '@/stores/projectStore'
import { ProjectSwitcher } from '@/features/workbench/components/ProjectSwitcher'

export function AppLayout() {
  const user = useAuthStore((s) => s.user)
  const currentProjectId = useProjectStore((s) => s.currentProjectId)
  const location = useLocation()

  const navItems = currentProjectId
    ? [
        { to: `/projects/${currentProjectId}`, icon: LayoutDashboard, label: '工作台' },
        { to: `/projects/${currentProjectId}/documents`, icon: FileText, label: '文档' },
        { to: `/projects/${currentProjectId}/skills`, icon: Sparkles, label: 'Skills' },
        { to: `/projects/${currentProjectId}/datasources`, icon: Plug, label: 'IM 接入' },
        { to: `/projects/${currentProjectId}/settings`, icon: Settings, label: '项目设置' },
      ]
    : []

  return (
    <div className="grid h-screen grid-rows-[56px_1fr] bg-bg-page">
      {/* 顶栏 (T03 完整实现) */}
      <header className="flex items-center justify-between border-b border-border-subtle bg-bg-card px-6">
        <div className="flex items-center gap-3">
          <Link to="/" className="font-content text-h3 text-text-primary">
            TokenKnows
          </Link>
          <span
            className="rounded-sm bg-success-bg px-1.5 py-0.5 font-ui text-micro font-medium text-success-dark"
            title="实例健康状态"
          >
            ●  实例健康 · v0.1
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* 项目切换器 (T03) - 在所有需要项目上下文的页面都可见 */}
          <ProjectSwitcher />

          {user ? (
            <div className="flex items-center gap-2">
              <span className="font-ui text-body-sm text-text-secondary">
                {user.display_name}
              </span>
              {user.is_instance_admin ? (
                <Link
                  to="/admin"
                  className="rounded-sm bg-inverse-bg px-2 py-0.5 font-ui text-micro font-medium text-inverse-text"
                  title="实例管理员"
                >
                  <Shield className="inline size-3" /> Admin
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>

      {/* 主区: 左侧栏 + 主内容 + 抽屉槽位 */}
      <div className="grid grid-cols-[200px_1fr] overflow-hidden">
        {/* 左侧导航 */}
        <nav className="border-r border-border-subtle bg-bg-card p-3" aria-label="主导航">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const isWorkbench = item.label === '工作台'
              const isActive =
                location.pathname === item.to ||
                (isWorkbench && location.pathname === '/') ||
                (!isWorkbench && location.pathname.startsWith(item.to + '/'))
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-3 py-2 font-ui text-body-sm transition',
                      isActive
                        ? 'bg-accent-primary-light text-accent-primary-dark'
                        : 'text-text-secondary hover:bg-bg-warm',
                    )}
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </Link>
                </li>
              )
            })}
            {navItems.length === 0 ? (
              <li className="px-3 py-2 font-ui text-caption text-text-subtle">
                选择或创建项目
              </li>
            ) : null}
          </ul>
        </nav>

        {/* 主内容 + 抽屉槽位 */}
        <main className="overflow-auto">
          <Outlet />
        </main>

        {/* 抽屉槽位 (T04 / T07 通过 portal 渲染到 #drawer-slot) */}
        <div id="drawer-slot" aria-hidden="true" />
      </div>
    </div>
  )
}
