/* eslint-disable react-refresh/only-export-components -- 路由文件
   本身导出 router 配置(非组件) + 定义本地 lazy 组件,
   这是标准 routes 文件模式,无法纯组件导出。HMR 影响仅限本文件。 */

/**
 * 路由表 · lazy + layouts + guards
 *
 * 设计依据: SharedFoundations.md §7
 *
 * 结构:
 *   - AuthLayout 包裹 /login /register /verify-email /forgot-password /reset-password
 *   - RequireAuth + AppLayout 包裹业务屏
 *   - RequireAuth + RequireRole(instance_admin) + AdminLayout 包裹 /admin/*
 *
 * 实际页面在 src/features/<域>/*Page.tsx,目前是 Placeholder,各任务实现时替换。
 */

import { createBrowserRouter, Navigate } from 'react-router-dom'
import { lazy, Suspense, type ReactNode } from 'react'
import { AuthLayout } from '@/components/layouts/AuthLayout'
import { AppLayout } from '@/components/layouts/AppLayout'
import { AdminLayout } from '@/components/layouts/AdminLayout'
import { RequireAuth } from '@/components/guards/RequireAuth'
import { RequireRole } from '@/components/guards/RequireRole'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'

// ── Auth ────────────────────────────────────────────────────────
const LoginPage = lazy(() => import('@/features/auth/LoginPage'))
const RegisterPage = lazy(() => import('@/features/auth/RegisterPage'))
const VerifyEmailPage = lazy(() => import('@/features/auth/VerifyEmailPage'))
const ForgotPasswordPage = lazy(() => import('@/features/auth/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('@/features/auth/ResetPasswordPage'))

// ── Business ───────────────────────────────────────────────────
const NewProjectPage = lazy(() => import('@/features/projects/NewProjectPage'))
const WorkbenchPage = lazy(() => import('@/features/workbench/WorkbenchPage'))
const DocumentListPage = lazy(() => import('@/features/documents/DocumentListPage'))
const DocumentPage = lazy(() => import('@/features/documents/DocumentPage'))
const ReviewPage = lazy(() => import('@/features/review/ReviewPage'))
const RedactionPage = lazy(() => import('@/features/redaction/RedactionPage'))
const PublishReceiptPage = lazy(() => import('@/features/publish/PublishReceiptPage'))
const ProjectSettingsPage = lazy(() => import('@/features/settings/ProjectSettingsPage'))

// ── Admin ──────────────────────────────────────────────────────
const AdminStatsPage = lazy(() => import('@/features/admin/AdminStatsPage'))
const AdminUsersPage = lazy(() => import('@/features/admin/AdminUsersPage'))
const AdminQuotasPage = lazy(() => import('@/features/admin/AdminQuotasPage'))
const AdminAuditPage = lazy(() => import('@/features/admin/AdminAuditPage'))

type LazyVariant = 'form' | 'workbench' | 'document' | 'list'

function Lazy({ children, variant = 'form' }: { children: ReactNode; variant?: LazyVariant }) {
  return <Suspense fallback={<LoadingSkeleton variant={variant} />}>{children}</Suspense>
}

export const router = createBrowserRouter([
  // ── 公开路由(认证) ─────────────────────────────────────────
  {
    element: <AuthLayout />,
    children: [
      { path: '/login',           element: <Lazy><LoginPage /></Lazy> },
      { path: '/register',        element: <Lazy><RegisterPage /></Lazy> },
      { path: '/verify-email',    element: <Lazy><VerifyEmailPage /></Lazy> },
      { path: '/forgot-password', element: <Lazy><ForgotPasswordPage /></Lazy> },
      { path: '/reset-password',  element: <Lazy><ResetPasswordPage /></Lazy> },
    ],
  },

  // ── 受保护的业务路由 ─────────────────────────────────────
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/',                                                   element: <Lazy variant="workbench"><WorkbenchPage /></Lazy> },
      { path: '/projects/new',                                       element: <Lazy><NewProjectPage /></Lazy> },
      { path: '/projects/:id',                                       element: <Lazy variant="workbench"><WorkbenchPage /></Lazy> },
      { path: '/projects/:id/documents',                             element: <Lazy variant="list"><DocumentListPage /></Lazy> },
      { path: '/projects/:id/documents/:docId',                      element: <Lazy variant="document"><DocumentPage /></Lazy> },
      {
        path: '/projects/:id/documents/:docId/review',
        element: (
          <RequireRole role="reviewer">
            <Lazy variant="document"><ReviewPage /></Lazy>
          </RequireRole>
        ),
      },
      { path: '/projects/:id/documents/:docId/redaction',            element: <Lazy variant="document"><RedactionPage /></Lazy> },
      { path: '/projects/:id/documents/:docId/published/:publishId', element: <Lazy variant="document"><PublishReceiptPage /></Lazy> },
      { path: '/projects/:id/settings/*',                            element: <Lazy><ProjectSettingsPage /></Lazy> },
    ],
  },

  // ── 实例管理员路由 ────────────────────────────────────────
  {
    element: (
      <RequireAuth>
        <RequireRole role="instance_admin">
          <AdminLayout />
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      { path: '/admin',         element: <Lazy variant="list"><AdminStatsPage /></Lazy> },
      { path: '/admin/users',   element: <Lazy variant="list"><AdminUsersPage /></Lazy> },
      { path: '/admin/quotas',  element: <Lazy variant="list"><AdminQuotasPage /></Lazy> },
      { path: '/admin/audit',   element: <Lazy variant="list"><AdminAuditPage /></Lazy> },
    ],
  },

  // ── 404 → / ────────────────────────────────────────────────
  { path: '*', element: <Navigate to="/" replace /> },
])
