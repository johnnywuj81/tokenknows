/**
 * MSW handlers · 聚合入口
 *
 * 设计依据: SharedFoundations.md §6
 *
 * 按 resource 分文件: handlers/auth.ts / projects.ts / events.ts / ...
 * 完整 API 清单见 docs/TDD.md §6.1
 *
 * 错误注入: URL 加 ?mock_error=<resource> 触发对应 resource 的 500。
 *
 * ⚠ assets 端点已切到真后端 (tokenknows-api on :8001).
 *   handlers/assets.ts 不再聚合 - generate / list / detail / chapters /
 *   status / SSE / delete / clone 全部穿透到 Vite proxy → :8001.
 */

import { authHandlers } from './handlers/auth'
import { projectHandlers } from './handlers/projects'
import { eventHandlers } from './handlers/events'
import { autoTriggerHandlers } from './handlers/auto-triggers'

export const handlers = [
  ...authHandlers,
  ...projectHandlers,
  ...eventHandlers,
  // ...assetHandlers, ← 切到真后端 (W2D7 联调)
  // v0.4 · auto-trigger REST API (后端 T32 未上线; MSW 兜底)
  ...autoTriggerHandlers,
  // ...其它 handler 在对应 sprint 加:
  // ...redactionHandlers,
  // ...publishHandlers,
  // ...adminHandlers,
]
