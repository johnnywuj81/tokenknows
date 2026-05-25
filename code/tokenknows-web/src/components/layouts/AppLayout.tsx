/**
 * AppLayout · 主业务屏 shell(T02-T13)。
 *
 * 设计依据: SharedFoundations.md §7.3
 * 顶栏 + 左侧导航 + 主区 + 抽屉槽位(React Portal target)
 *
 * 顶栏内容(实例信息 + 项目选择 + 用户)在 T03 完整实现,
 * 这里只搭骨架,文字占位。
 */

import { useState, type ComponentType } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { LayoutDashboard, FileText, Sparkles, Plug, Settings, Shield, Inbox, BarChart3, Globe, Network, ChevronRight, ChevronDown, LogOut } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { useProjectStore } from '@/stores/projectStore'
import { ProjectSwitcher } from '@/features/workbench/components/ProjectSwitcher'
import { WithdrawNotification } from '@/features/auto-triggers/WithdrawNotification'
import { NotificationBell } from '@/features/notifications/NotificationBell'

interface NavLeaf {
  to: string
  icon: ComponentType<{ className?: string }>
  label: string
}

interface NavGroup {
  /** group id, 用于展开 state */
  id: string
  icon: ComponentType<{ className?: string }>
  label: string
  /** group 自己有路由时, 点 group header 直接跳; 没的话仅展开/收起. */
  to?: string
  children: NavLeaf[]
}

type NavItem = NavLeaf | NavGroup

function isGroup(item: NavItem): item is NavGroup {
  return 'children' in item
}

export function AppLayout() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const currentProjectId = useProjectStore((s) => s.currentProjectId)

  // T145: 顶栏退出登录入口. 之前 UI 不暴露 logout, 用户只能 console 删
  // localStorage. 现在用 shadcn DropdownMenu 包 display_name, 下拉里加退出.
  function handleLogout(): void {
    logout()                          // 清 authStore (含 persist localStorage)
    queryClient.clear()               // 清 TanStack Query cache, 防泄露上一用户数据
    navigate('/login', { replace: true })
  }
  const location = useLocation()

  // T123: Skills 类聚成嵌套 group (审批收件箱 / 治理 / 市场 都是 Skills 子项)
  const navItems: NavItem[] = currentProjectId
    ? [
        { to: `/projects/${currentProjectId}`, icon: LayoutDashboard, label: '工作台' },
        { to: `/projects/${currentProjectId}/documents`, icon: FileText, label: '文档' },
        {
          id: 'skills',
          icon: Sparkles,
          label: 'Skills',
          to: `/projects/${currentProjectId}/skills`,
          children: [
            { to: `/projects/${currentProjectId}/skills/review-inbox`, icon: Inbox, label: '审批收件箱' },
            { to: `/projects/${currentProjectId}/skills/governance`, icon: BarChart3, label: '治理' },
            { to: `/skills/marketplace`, icon: Globe, label: '市场' },
          ],
        },
        { to: `/global-entities`, icon: Network, label: '全局实体' },
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

          {/* v0.5.1 T51 · 通知铃铛 (consent_* 事件) */}
          {user ? <NotificationBell /> : null}

          {user ? (
            <div className="flex items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex items-center gap-1 rounded-md px-2 py-1 font-ui text-body-sm text-text-secondary transition hover:bg-bg-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                    aria-label="用户菜单"
                  >
                    {user.display_name}
                    <ChevronDown className="size-3.5 text-text-muted" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
                    {user.display_name}
                  </DropdownMenuLabel>
                  {/* T145: 不放 '个人设置' 入口, 后端无对应路由, 加了点了 404.
                      用户个人设置真要做时再加 /settings/profile 路由 + item. */}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={handleLogout}
                    className="font-ui text-body-sm text-danger focus:text-danger"
                  >
                    <LogOut className="size-3.5" />
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
        {/* 左侧导航 (T123: Skills 类用嵌套 group) */}
        <nav className="border-r border-border-subtle bg-bg-card p-3" aria-label="主导航">
          <ul className="space-y-1">
            {navItems.map((item) => (
              isGroup(item) ? (
                <NavGroupItem key={item.id} group={item} pathname={location.pathname} />
              ) : (
                <NavLeafItem key={item.to} leaf={item} pathname={location.pathname} />
              )
            ))}
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

        {/* v0.4 体验要素 #30 · 撤回窗口浮动通知卡 (右下角) */}
        <WithdrawNotification />
      </div>
    </div>
  )
}


// ── nav 子组件 ────────────────────────────────────────────────────


/** 叶子节点 (无子项); 路由匹配规则: exact match 或 prefix + '/'. */
function NavLeafItem({ leaf, pathname }: { leaf: NavLeaf; pathname: string }) {
  const isWorkbench = leaf.label === '工作台'
  const isActive =
    pathname === leaf.to ||
    (isWorkbench && pathname === '/') ||
    (!isWorkbench && pathname.startsWith(leaf.to + '/'))
  return (
    <li>
      <Link
        to={leaf.to}
        className={cn(
          'flex items-center gap-2 rounded-md px-3 py-2 font-ui text-body-sm transition',
          isActive
            ? 'bg-accent-primary-light text-accent-primary-dark'
            : 'text-text-secondary hover:bg-bg-warm',
        )}
      >
        <leaf.icon className="size-4" />
        {leaf.label}
      </Link>
    </li>
  )
}


/** 可折叠 group; 默认按当前路由是否命中子项自动展开. */
function NavGroupItem({ group, pathname }: { group: NavGroup; pathname: string }) {
  // 路径在 group 自己 to 上 (e.g. /projects/x/skills) 或任一 child → 展开
  const isSelfActive = !!group.to && (
    pathname === group.to || pathname.startsWith(group.to + '/')
  )
  const anyChildActive = group.children.some(
    (c) => pathname === c.to || pathname.startsWith(c.to + '/'),
  )
  const isGroupActive = isSelfActive || anyChildActive
  // 默认: 命中则展开
  const [expanded, setExpanded] = useState(isGroupActive)

  return (
    <li>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        data-testid={`nav-group-${group.id}`}
        className={cn(
          'flex w-full items-center gap-2 rounded-md px-3 py-2 font-ui text-body-sm transition text-left',
          isGroupActive && !anyChildActive
            ? 'bg-accent-primary-light text-accent-primary-dark'
            : 'text-text-secondary hover:bg-bg-warm',
        )}
      >
        <group.icon className="size-4" />
        <span className="flex-1">{group.label}</span>
        <ChevronRight
          className={cn(
            'size-3 shrink-0 text-text-subtle transition-transform',
            expanded && 'rotate-90',
          )}
        />
      </button>
      {expanded ? (
        <ul className="mt-0.5 ml-2 space-y-0.5 border-l border-border-subtle pl-2">
          {/* group.to 存在时, 第 1 项是 group 自己 ("Skill 列表") */}
          {group.to ? (
            <li>
              <Link
                to={group.to}
                className={cn(
                  'flex items-center gap-2 rounded-md px-2 py-1.5 font-ui text-caption transition',
                  isSelfActive
                    ? 'bg-accent-primary-light text-accent-primary-dark'
                    : 'text-text-secondary hover:bg-bg-warm',
                )}
              >
                Skill 列表
              </Link>
            </li>
          ) : null}
          {group.children.map((c) => {
            const childActive = pathname === c.to || pathname.startsWith(c.to + '/')
            return (
              <li key={c.to}>
                <Link
                  to={c.to}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2 py-1.5 font-ui text-caption transition',
                    childActive
                      ? 'bg-accent-primary-light text-accent-primary-dark'
                      : 'text-text-secondary hover:bg-bg-warm',
                  )}
                >
                  <c.icon className="size-3.5" />
                  {c.label}
                </Link>
              </li>
            )
          })}
        </ul>
      ) : null}
    </li>
  )
}
