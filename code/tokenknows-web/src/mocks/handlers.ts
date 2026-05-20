/**
 * MSW handlers · 聚合入口
 *
 * 设计依据: SharedFoundations.md §6
 *
 * 按 resource 分文件: handlers/auth.ts / projects.ts / events.ts / ...
 * W1D1 只有 auth.ts;其它任务在对应 sprint 加。
 *
 * 完整 API 清单见 docs/TDD.md §6.1
 *
 * 错误注入: URL 加 ?mock_error=<resource> 触发对应 resource 的 500。
 */

import { authHandlers } from './handlers/auth'
import { projectHandlers } from './handlers/projects'
import { eventHandlers } from './handlers/events'
import { assetHandlers } from './handlers/assets'

export const handlers = [
  ...authHandlers,
  ...projectHandlers,
  ...eventHandlers,
  ...assetHandlers,
  // ...其它 handler 在对应 sprint 加:
  // ...redactionHandlers,
  // ...publishHandlers,
  // ...adminHandlers,
]
