/**
 * Layouts · AuthLayout + AppLayout + AdminLayout.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { AuthLayout } from './AuthLayout'
import { AppLayout } from './AppLayout'
import { AdminLayout } from './AdminLayout'
import { useAuthStore } from '@/stores/authStore'
import { useProjectStore } from '@/stores/projectStore'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode, path = '/') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route element={ui}>
            <Route path="/" element={<div data-testid="content">CONTENT</div>} />
            <Route path="/admin" element={<div data-testid="content">ADMIN</div>} />
            <Route path="/admin/users" element={<div data-testid="content">USERS</div>} />
            <Route path="/projects/:id" element={<div data-testid="content">PROJ</div>} />
            <Route path="/projects/:id/documents" element={<div data-testid="content">DOCS</div>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


// ─── AuthLayout ───────────────────────────────────────────


describe('AuthLayout', () => {
  it('renders brand + outlet content', () => {
    render(withWrappers(<AuthLayout />))
    expect(screen.getByText('TokenKnows')).toBeInTheDocument()
    expect(screen.getByText(/把研发过程/)).toBeInTheDocument()
    expect(screen.getByTestId('content').textContent).toBe('CONTENT')
  })

  it('quote rendered', () => {
    render(withWrappers(<AuthLayout />))
    expect(screen.getByText(/不浪费一滴大模型 token/)).toBeInTheDocument()
  })
})


// ─── AppLayout ────────────────────────────────────────────


describe('AppLayout', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAuthStore.setState({
      user: {
        id: 'u1', email: 'a@b.com', display_name: 'Alice',
        is_instance_admin: false, created_at: '', updated_at: '',
      },
      accessToken: 'tk',
      isAuthenticated: true,
    })
    useProjectStore.setState({ currentProjectId: null })
  })

  it('renders header + brand + user name', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<AppLayout />))
    expect(screen.getByText('TokenKnows')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText(/实例健康/)).toBeInTheDocument()
  })

  it('no current project: shows 选择或创建项目', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    render(withWrappers(<AppLayout />))
    expect(screen.getByText('选择或创建项目')).toBeInTheDocument()
  })

  it('with currentProjectId: shows 3 nav items', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    useProjectStore.setState({ currentProjectId: 'p1' })
    render(withWrappers(<AppLayout />, '/projects/p1'))
    expect(screen.getByText('工作台')).toBeInTheDocument()
    expect(screen.getByText('文档')).toBeInTheDocument()
    expect(screen.getByText('项目设置')).toBeInTheDocument()
  })

  it('is_instance_admin: shows Admin link', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    useAuthStore.setState({
      user: {
        id: 'u1', email: 'a@b.com', display_name: 'Alice',
        is_instance_admin: true, created_at: '', updated_at: '',
      },
      accessToken: 'tk',
      isAuthenticated: true,
    })
    render(withWrappers(<AppLayout />))
    expect(screen.getByText(/Admin/)).toBeInTheDocument()
  })

  it('drawer slot rendered', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    const { container } = render(withWrappers(<AppLayout />))
    expect(container.querySelector('#drawer-slot')).not.toBeNull()
  })
})


// ─── AdminLayout ──────────────────────────────────────────


describe('AdminLayout', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: 'u1', email: 'admin@b.com', display_name: 'Admin',
        is_instance_admin: true, created_at: '', updated_at: '',
      },
      accessToken: 'tk',
      isAuthenticated: true,
    })
  })

  it('renders dark header + 4 sub-nav links', () => {
    render(withWrappers(<AdminLayout />, '/admin'))
    expect(screen.getByText('TokenKnows')).toBeInTheDocument()
    expect(screen.getByText('实例管理')).toBeInTheDocument()
    expect(screen.getByText('统计')).toBeInTheDocument()
    expect(screen.getByText('用户')).toBeInTheDocument()
    expect(screen.getByText('配额')).toBeInTheDocument()
    expect(screen.getByText('审计')).toBeInTheDocument()
  })

  it('退出管理 link rendered', () => {
    render(withWrappers(<AdminLayout />, '/admin'))
    expect(screen.getByText('退出管理')).toBeInTheDocument()
  })

  it('non-admin user: redirects (no admin content)', () => {
    useAuthStore.setState({
      user: {
        id: 'u1', email: 'a@b.com', display_name: 'A',
        is_instance_admin: false, created_at: '', updated_at: '',
      },
      isAuthenticated: true,
    })
    render(withWrappers(<AdminLayout />, '/admin'))
    expect(screen.queryByText('实例管理')).toBeNull()
  })

  it('admin name visible', () => {
    render(withWrappers(<AdminLayout />, '/admin'))
    expect(screen.getByText('Admin')).toBeInTheDocument()
  })
})
