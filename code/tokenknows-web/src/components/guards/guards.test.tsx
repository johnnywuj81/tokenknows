/**
 * RequireAuth + RequireRole 单测 · 路由守卫.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RequireAuth } from './RequireAuth'
import { RequireRole } from './RequireRole'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types/api'


const mockUser: User = {
  id: 'u1', email: 'x@y', display_name: 'X',
  is_instance_admin: false,
  email_verified_at: null,
  created_at: '', updated_at: '',
}

const adminUser: User = { ...mockUser, is_instance_admin: true }


beforeEach(() => {
  localStorage.clear()
  useAuthStore.getState().logout()
})


function Routed({ initialPath = '/protected', children }: {
  initialPath?: string
  children: React.ReactNode
}) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>LOGIN_PAGE</div>} />
        <Route path="/" element={<div>HOME</div>} />
        <Route path="/protected" element={children as React.ReactElement} />
        <Route path="/admin" element={children as React.ReactElement} />
      </Routes>
    </MemoryRouter>
  )
}


describe('RequireAuth', () => {
  it('renders children when authenticated', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok')
    Routed({
      initialPath: '/protected',
      children: (
        <RequireAuth>
          <div>SECRET</div>
        </RequireAuth>
      ),
    })
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route path="/login" element={<div>LOGIN_PAGE</div>} />
          <Route path="/protected" element={
            <RequireAuth>
              <div>SECRET</div>
            </RequireAuth>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('SECRET')).toBeInTheDocument()
  })

  it('redirects to /login when unauthenticated', () => {
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route path="/login" element={<div>LOGIN_PAGE</div>} />
          <Route path="/protected" element={
            <RequireAuth>
              <div>SECRET</div>
            </RequireAuth>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('LOGIN_PAGE')).toBeInTheDocument()
    expect(screen.queryByText('SECRET')).toBeNull()
  })
})


describe('RequireRole', () => {
  it('redirects to /login when not authenticated', () => {
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/login" element={<div>LOGIN_PAGE</div>} />
          <Route path="/admin" element={
            <RequireRole role="instance_admin">
              <div>ADMIN_PAGE</div>
            </RequireRole>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('LOGIN_PAGE')).toBeInTheDocument()
  })

  it('redirects to / when instance_admin required but user is not', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok')
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/" element={<div>HOME</div>} />
          <Route path="/admin" element={
            <RequireRole role="instance_admin">
              <div>ADMIN_PAGE</div>
            </RequireRole>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('HOME')).toBeInTheDocument()
    expect(screen.queryByText('ADMIN_PAGE')).toBeNull()
  })

  it('renders admin page when user is instance_admin', () => {
    useAuthStore.getState().setAuth(adminUser, 'tok')
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/admin" element={
            <RequireRole role="instance_admin">
              <div>ADMIN_PAGE</div>
            </RequireRole>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('ADMIN_PAGE')).toBeInTheDocument()
  })

  it('passes through for non-admin roles (reviewer/owner) — frontend lets page do 2nd check', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok')
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route path="/protected" element={
            <RequireRole role="reviewer">
              <div>REVIEWER_PAGE</div>
            </RequireRole>
          } />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('REVIEWER_PAGE')).toBeInTheDocument()
  })
})
