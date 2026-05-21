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
