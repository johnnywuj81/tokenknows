/**
 * api.ts · 401 自动 logout + redirect 跳登录分支测试.
 *
 * jsdom 不支持真 navigation; 我们用 Object.defineProperty 覆盖 window.location 来断言.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import { api } from './api'
import { useAuthStore } from '@/stores/authStore'


describe('api 401 redirect branch', () => {
  let mock: MockAdapter
  let originalLocation: Location
  let hrefSetter: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mock = new MockAdapter(api)
    useAuthStore.setState({
      accessToken: 'tk',
      user: { id: 'u1', email: 'a@b.com', display_name: 'A', role: 'editor' },
      isAuthenticated: true,
    })
    originalLocation = window.location
    // Override window.location to capture href setter calls
    hrefSetter = vi.fn()
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        pathname: '/projects/p1',
        search: '?x=1',
        set href(v: string) { hrefSetter(v) },
        get href() { return originalLocation.href },
      },
    })
  })

  afterEach(() => {
    mock.restore()
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  it('401 not on /login: triggers logout + href redirect with encoded path', async () => {
    mock.onGet('/test').reply(401, {})
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout')
    try {
      await api.get('/test')
    } catch (err) {
      expect(err).toMatchObject({ code: 'UNAUTHORIZED', status: 401 })
    }
    expect(logoutSpy).toHaveBeenCalled()
    expect(hrefSetter).toHaveBeenCalledWith(
      expect.stringContaining('/login?redirect='),
    )
    expect(hrefSetter.mock.calls[0][0]).toContain(encodeURIComponent('/projects/p1?x=1'))
  })

  it('401 on /login: does NOT redirect (already there)', async () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        pathname: '/login',
        search: '',
        set href(v: string) { hrefSetter(v) },
        get href() { return originalLocation.href },
      },
    })
    mock.onGet('/test').reply(401, {})
    try { await api.get('/test') } catch {}
    expect(hrefSetter).not.toHaveBeenCalled()
  })
})
