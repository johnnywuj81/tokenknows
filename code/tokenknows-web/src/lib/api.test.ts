/**
 * api.ts 单测 · isApiError / getErrorMessage / normalize 错误归一.
 *
 * axios interceptor 的真打不易测; 测两个 exported helpers 即可.
 */

import { describe, it, expect } from 'vitest'
import { getErrorMessage, isApiError, api } from './api'

describe('isApiError', () => {
  it('true for valid ApiError shape', () => {
    expect(isApiError({ code: 'NOT_FOUND', status: 404, message: 'x' })).toBe(true)
  })

  it('false for plain Error', () => {
    expect(isApiError(new Error('boom'))).toBe(false)
  })

  it('false for null / undefined / string / number', () => {
    expect(isApiError(null)).toBe(false)
    expect(isApiError(undefined)).toBe(false)
    expect(isApiError('error string')).toBe(false)
    expect(isApiError(42)).toBe(false)
  })

  it('false when missing code or status', () => {
    expect(isApiError({ code: 'NOT_FOUND' })).toBe(false)
    expect(isApiError({ status: 404 })).toBe(false)
  })
})


describe('getErrorMessage', () => {
  it('returns string directly', () => {
    expect(getErrorMessage('网络断开')).toBe('网络断开')
  })

  it('extracts .message from {message: ...}', () => {
    expect(getErrorMessage({ message: 'API down' })).toBe('API down')
  })

  it('extracts from Error instance', () => {
    expect(getErrorMessage(new Error('boom'))).toBe('boom')
  })

  it('falls back to 未知错误', () => {
    expect(getErrorMessage(42)).toBe('未知错误')
    expect(getErrorMessage(null)).toBe('未知错误')
    expect(getErrorMessage(undefined)).toBe('未知错误')
  })

  it('handles ApiError shape', () => {
    expect(
      getErrorMessage({ code: 'NOT_FOUND', status: 404, message: '资源不存在' }),
    ).toBe('资源不存在')
  })
})


describe('api instance', () => {
  it('exports axios instance with baseURL /api/v1', () => {
    expect(api.defaults.baseURL).toBe('/api/v1')
  })

  it('has Content-Type json default', () => {
    expect(api.defaults.headers['Content-Type']).toBe('application/json')
  })

  it('has 30s timeout', () => {
    expect(api.defaults.timeout).toBe(30_000)
  })
})


// ─── interceptor error normalize (整合测试通过真发请求 → 拦截器) ────


import { useAuthStore } from '@/stores/authStore'
import { vi, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'

describe('api interceptor · error normalization', () => {
  let mock: MockAdapter

  beforeEach(() => {
    mock = new MockAdapter(api)
    useAuthStore.setState({ accessToken: null, user: null })
  })

  afterEach(() => {
    mock.restore()
  })

  it('NETWORK_ERROR when no response (status 0)', async () => {
    mock.onGet('/test').networkError()
    try {
      await api.get('/test')
    } catch (err) {
      expect(err).toMatchObject({
        code: 'NETWORK_ERROR',
        status: 0,
        message: '网络异常,请检查连接',
      })
    }
  })

  it('400 → BAD_REQUEST default message', async () => {
    mock.onGet('/test').reply(400, {})
    try {
      await api.get('/test')
    } catch (err) {
      expect(err).toMatchObject({
        code: 'BAD_REQUEST',
        status: 400,
        message: '请求参数有误',
      })
    }
  })

  it('404 → NOT_FOUND default message', async () => {
    mock.onGet('/test').reply(404, {})
    try {
      await api.get('/test')
    } catch (err) {
      expect(err).toMatchObject({ code: 'NOT_FOUND', message: '资源不存在' })
    }
  })

  it('403 → FORBIDDEN', async () => {
    mock.onGet('/test').reply(403, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'FORBIDDEN', message: '无权访问该资源' })
    }
  })

  it('409 → CONFLICT', async () => {
    mock.onGet('/test').reply(409, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'CONFLICT' })
    }
  })

  it('422 → VALIDATION_ERROR', async () => {
    mock.onGet('/test').reply(422, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'VALIDATION_ERROR' })
    }
  })

  it('429 → RATE_LIMITED', async () => {
    mock.onGet('/test').reply(429, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'RATE_LIMITED' })
    }
  })

  it('500 → SERVER_ERROR', async () => {
    mock.onGet('/test').reply(500, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'SERVER_ERROR' })
    }
  })

  it('uses backend code/detail when present', async () => {
    mock.onGet('/test').reply(409, { code: 'EGRESS_DENIED', detail: '出域禁用' })
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'EGRESS_DENIED', message: '出域禁用' })
    }
  })

  it('unknown status (e.g. 418) → SERVER_ERROR fallback', async () => {
    mock.onGet('/test').reply(418, {})
    try { await api.get('/test') } catch (err) {
      expect(err).toMatchObject({ code: 'SERVER_ERROR' })
    }
  })

  it('injects Authorization header when accessToken set', async () => {
    useAuthStore.setState({ accessToken: 'tk-abc' })
    mock.onGet('/test').reply((config) => {
      expect(config.headers?.Authorization).toBe('Bearer tk-abc')
      return [200, {}]
    })
    await api.get('/test')
  })

  it('no Authorization when no token', async () => {
    mock.onGet('/test').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined()
      return [200, {}]
    })
    await api.get('/test')
  })
})
