/**
 * Mock fixtures · 测试用户。
 * 单一开发账号,T01 实现时扩展到 2-3 个角色覆盖。
 */

import type { User } from '@/types/api'

export const fixtureUsers: User[] = [
  {
    id: 'user-001',
    email: 'demo@tokenknows.local',
    display_name: '示例用户',
    is_instance_admin: true,           // MVP 演示阶段给 admin 方便看 T15
    email_verified_at: '2026-05-19T10:00:00Z',
    created_at: '2026-05-19T10:00:00Z',
    updated_at: '2026-05-20T10:00:00Z',
  },
]

export const DEFAULT_USER = fixtureUsers[0]

// 用于 mock JWT token (前端不验签,后端联调时换真 token)
export const MOCK_ACCESS_TOKEN = 'mock.access.token.dev'
export const MOCK_REFRESH_TOKEN = 'mock.refresh.token.dev'
