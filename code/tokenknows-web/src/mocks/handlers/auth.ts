/**
 * MSW handlers · auth + me
 *
 * 设计依据: SharedFoundations.md §6 + tasks/T01-auth.md §4
 * 错误注入: URL ?mock_error=auth → 触发 500
 */

import { http, HttpResponse } from 'msw'
import { DEFAULT_USER, MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN, fixtureUsers } from '../fixtures/users'

const ERROR_MODE = typeof window !== 'undefined'
  ? new URLSearchParams(window.location.search).get('mock_error')
  : null

const BASE = '/api/v1'

export const authHandlers = [
  // ── 注册 ─────────────────────────────────────────────────────
  http.post(`${BASE}/auth/register`, async ({ request }) => {
    if (ERROR_MODE === 'auth') {
      return HttpResponse.json({ code: 'SERVER_ERROR', detail: 'mocked 500' }, { status: 500 })
    }
    const body = (await request.json()) as { email: string; password: string; display_name: string }

    // 邮箱已存在 → 409
    if (fixtureUsers.some((u) => u.email === body.email)) {
      return HttpResponse.json(
        { code: 'CONFLICT', detail: '邮箱已注册' },
        { status: 409 },
      )
    }

    // 创建 (内存,刷新页丢)
    const now = new Date().toISOString()
    const newUser = {
      id: `user-${Math.random().toString(36).slice(2, 10)}`,
      email: body.email,
      display_name: body.display_name,
      is_instance_admin: false,
      email_verified_at: null,
      created_at: now,
      updated_at: now,
    }
    fixtureUsers.push(newUser)

    return HttpResponse.json({ user: newUser, requires_verification: true })
  }),

  // ── 登录 ─────────────────────────────────────────────────────
  http.post(`${BASE}/auth/login`, async ({ request }) => {
    if (ERROR_MODE === 'auth') {
      return HttpResponse.json({ code: 'SERVER_ERROR', detail: 'mocked 500' }, { status: 500 })
    }
    const body = (await request.json()) as { email: string; password: string }

    // mock 任意密码都通过,只要邮箱存在
    const user = fixtureUsers.find((u) => u.email === body.email) ?? DEFAULT_USER

    return HttpResponse.json({
      access_token: MOCK_ACCESS_TOKEN,
      refresh_token: MOCK_REFRESH_TOKEN,
      user,
    })
  }),

  // ── 登出 ─────────────────────────────────────────────────────
  http.post(`${BASE}/auth/logout`, () => {
    return HttpResponse.json({ ok: true })
  }),

  // ── refresh ──────────────────────────────────────────────────
  http.post(`${BASE}/auth/refresh`, () => {
    return HttpResponse.json({
      access_token: MOCK_ACCESS_TOKEN,
      refresh_token: MOCK_REFRESH_TOKEN,
    })
  }),

  // ── 邮箱验证 ───────────────────────────────────────────────
  http.post(`${BASE}/me/verify-email`, async ({ request }) => {
    const body = (await request.json()) as { token: string }
    if (!body.token || body.token === 'invalid') {
      return HttpResponse.json(
        { code: 'BAD_REQUEST', detail: 'token 无效或已过期' },
        { status: 400 },
      )
    }
    return HttpResponse.json({ ok: true, verified_at: new Date().toISOString() })
  }),

  // ── 找回密码 / 重置 ─────────────────────────────────────
  http.post(`${BASE}/auth/forgot-password`, async () => {
    return HttpResponse.json({ ok: true, message: '邮件已发送' })
  }),

  http.post(`${BASE}/auth/reset-password`, async ({ request }) => {
    const body = (await request.json()) as { token: string; new_password: string }
    if (!body.token || body.token === 'invalid') {
      return HttpResponse.json(
        { code: 'BAD_REQUEST', detail: 'token 无效或已过期' },
        { status: 400 },
      )
    }
    return HttpResponse.json({ ok: true })
  }),

  // ── 当前用户 ────────────────────────────────────────────
  http.get(`${BASE}/me`, ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth || !auth.startsWith('Bearer ')) {
      return HttpResponse.json(
        { code: 'UNAUTHORIZED', detail: '未登录' },
        { status: 401 },
      )
    }
    return HttpResponse.json(DEFAULT_USER)
  }),
]
