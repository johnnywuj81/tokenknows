/**
 * Routes · createBrowserRouter config smoke test.
 */

import { describe, it, expect } from 'vitest'
import { router } from './index'


describe('router config', () => {
  it('exports a router', () => {
    expect(router).toBeDefined()
    expect(router.routes).toBeDefined()
  })

  it('has 4 top-level route groups (auth + protected + admin + 404)', () => {
    expect(router.routes.length).toBe(4)
  })

  it('auth group has 5 children (login + register + verify + forgot + reset)', () => {
    const auth = router.routes[0]
    expect(auth.children?.length).toBe(5)
    const paths = (auth.children ?? []).map((c) => c.path)
    expect(paths).toContain('/login')
    expect(paths).toContain('/register')
    expect(paths).toContain('/verify-email')
    expect(paths).toContain('/forgot-password')
    expect(paths).toContain('/reset-password')
  })

  it('protected group has business routes', () => {
    const protectedGroup = router.routes[1]
    const paths = (protectedGroup.children ?? []).map((c) => c.path)
    expect(paths).toContain('/')
    expect(paths).toContain('/projects/new')
    expect(paths).toContain('/projects/:id')
    expect(paths).toContain('/projects/:id/documents')
    expect(paths).toContain('/projects/:id/documents/:docId')
    expect(paths).toContain('/projects/:id/documents/:docId/review')
    expect(paths).toContain('/projects/:id/documents/:docId/redaction')
    expect(paths).toContain('/projects/:id/documents/:docId/published/:publishId')
    expect(paths).toContain('/projects/:id/settings/*')
  })

  it('admin group has 4 admin pages', () => {
    const admin = router.routes[2]
    expect(admin.children?.length).toBe(4)
    const paths = (admin.children ?? []).map((c) => c.path)
    expect(paths).toContain('/admin')
    expect(paths).toContain('/admin/users')
    expect(paths).toContain('/admin/quotas')
    expect(paths).toContain('/admin/audit')
  })

  it('404 catch-all on path=*', () => {
    const wildcard = router.routes[3]
    expect(wildcard.path).toBe('*')
  })
})
