/**
 * RequireRole · 角色守卫(前端 UX 拦截,后端再校验)。
 *
 * 设计依据: SharedFoundations.md §7.2
 *
 * MVP 仅校验 instance_admin;reviewer / owner 需要项目级 membership,
 * 由具体页面在 useQuery 里读 project.role 二次确认。
 */

import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

type Role = 'instance_admin' | 'reviewer' | 'owner'

interface RequireRoleProps {
  role: Role
  children?: React.ReactNode
}

export function RequireRole({ role, children }: RequireRoleProps) {
  const user = useAuthStore((s) => s.user)

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (role === 'instance_admin' && !user.is_instance_admin) {
    return <Navigate to="/" replace />
  }

  // reviewer / owner 由页面二次校验
  return children ? <>{children}</> : <Outlet />
}
