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

import { http, HttpResponse } from 'msw'
import { authHandlers } from './handlers/auth'
import { projectHandlers } from './handlers/projects'
import { eventHandlers } from './handlers/events'

/**
 * MSW worker liveness probe.
 *
 * main.tsx 的 watchdog 每 30s 打这个 URL:
 *   - 200 + {msw:true}  → SW 健康
 *   - 其它(真后端 404 / 网络错) → SW 死了, 自动 unregister + reload
 * 见 MSW + Vite HMR 老 bug: SW 注册了但 fetch handler 未生效.
 */
const livenessProbe = http.get('/api/v1/__msw_health__', () =>
  HttpResponse.json({ msw: true, ts: Date.now() }),
)

export const handlers = [
  livenessProbe,
  ...authHandlers,
  ...projectHandlers,
  ...eventHandlers,
  // ...assetHandlers, ← 切到真后端 (W2D7 联调)
  // ...autoTriggerHandlers, ← v0.4 T32 已上线, 切到真后端
  //   保留 handlers/auto-triggers.ts + fixtures/auto-triggers.ts 作 v0.5 多实例
  //   场景或 staging 离线 demo 用; 当前 vite proxy 透传到 :8001
  // ...其它 handler 在对应 sprint 加:
  // ...redactionHandlers,
  // ...publishHandlers,
  // ...adminHandlers,
]
