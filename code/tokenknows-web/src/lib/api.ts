/**
 * axios HTTP 客户端 · 请求 / 响应 interceptor + 错误归一 + 401 自动跳转。
 *
 * 设计依据: SharedFoundations.md §2
 *
 * 用法:
 *   import { api } from '@/lib/api'
 *   const { data } = await api.get<ApiResponse<Project[]>>('/projects')
 */

import axios, { type AxiosError, type AxiosInstance } from 'axios'
import type { ApiError, ErrorCode } from '@/types/api'
import { useAuthStore } from '@/stores/authStore'

export const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor · 注入 Authorization + X-User-Id (v0.9 T67) ──
api.interceptors.request.use((config) => {
  const state = useAuthStore.getState()
  const token = state.accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // v0.9 MVP: 后端用 X-User-Id 解 session (未来 JWT subject)
  if (state.user?.id) {
    config.headers['X-User-Id'] = state.user.id
  }
  return config
})

// ── Response interceptor · 错误归一 + 401 自动跳登录 ─────────────
api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<{ detail?: string; code?: ErrorCode }>) => {
    const apiErr = normalizeError(error)

    // 401 自动 logout + 跳登录 (保留 redirect)
    if (
      apiErr.status === 401 &&
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login')
    ) {
      useAuthStore.getState().logout()
      const redirect = window.location.pathname + window.location.search
      window.location.href = `/login?redirect=${encodeURIComponent(redirect)}`
    }

    return Promise.reject(apiErr)
  },
)

// ── Error 归一化 ──────────────────────────────────────────────────

function normalizeError(error: AxiosError<{ detail?: string; code?: ErrorCode }>): ApiError {
  // 网络错误 (无 response)
  if (!error.response) {
    return {
      code: 'NETWORK_ERROR',
      message: '网络异常,请检查连接',
      detail: error.message,
      status: 0,
    }
  }

  const status = error.response.status
  const code = error.response.data?.code ?? mapStatusToCode(status)
  const message = error.response.data?.detail ?? defaultMessage(code)

  return {
    code,
    message,
    detail: error.response.data,
    status,
  }
}

function mapStatusToCode(status: number): ErrorCode {
  if (status === 400) return 'BAD_REQUEST'
  if (status === 401) return 'UNAUTHORIZED'
  if (status === 403) return 'FORBIDDEN'
  if (status === 404) return 'NOT_FOUND'
  if (status === 409) return 'CONFLICT'
  if (status === 422) return 'VALIDATION_ERROR'
  if (status === 429) return 'RATE_LIMITED'
  if (status >= 500) return 'SERVER_ERROR'
  return 'SERVER_ERROR'
}

function defaultMessage(code: ErrorCode): string {
  switch (code) {
    case 'BAD_REQUEST': return '请求参数有误'
    case 'UNAUTHORIZED': return '请重新登录'
    case 'FORBIDDEN': return '无权访问该资源'
    case 'NOT_FOUND': return '资源不存在'
    case 'CONFLICT': return '资源冲突,请刷新后重试'
    case 'VALIDATION_ERROR': return '数据校验失败'
    case 'RATE_LIMITED': return '请求过于频繁,请稍后再试'
    case 'SERVER_ERROR': return '服务暂不可用'
    case 'NETWORK_ERROR': return '网络异常'
    case 'EGRESS_DENIED': return '云端模型出域已被禁用,已自动切换到本地模型'
    case 'LICENSE_EXPIRED': return '凭证已过期,实例进入只读模式'
    default: return '未知错误'
  }
}

// ── 工具函数 ─────────────────────────────────────────────────────

/**
 * 从 unknown error 中提取可读消息(给 UI 显示)。
 * 用于 TanStack Query / mutation 的 onError 回调。
 */
export function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message)
  }
  return '未知错误'
}

/**
 * 判断 unknown error 是否为 ApiError 形态。
 */
export function isApiError(error: unknown): error is ApiError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'status' in error
  )
}
