/**
 * Stats / Todos handlers · 工作台 (T03)
 *
 * 注意 (Plugin Integration 后):
 *   - events 接口 (GET /projects/:id/events + GET /events/:id) 已切换到
 *     真后端 (Claude Code 插件 → SQLite events 表).
 *   - 本文件只保留 stats / todos 两个 mock, 等后端补全后再去掉.
 *
 * 设计依据:
 *   - TDD §6.1: GET /projects/:id/stats + GET /projects/:id/todos
 *   - SharedFoundations §5.3: queryKey 表
 */

import { http, HttpResponse, delay } from 'msw'
import type { ProjectStats, TodoItem } from '@/types/api'
import { fixtureTodos } from '../fixtures/todos'

const BASE = '/api/v1'

// MVP 简单 stats (events 数走真后端时这里不再准确; 待后端补 /stats 端点)
function statsForProject(_projectId: string): ProjectStats {
  return {
    events_this_week: 0,    // 真值在浏览器拉 /events?from=... 算
    assets_pending_review: 2,
    datasources_total: 3,
    datasources_healthy: 3,
  }
}

export const eventHandlers = [
  // 项目统计 (events_this_week 待后端补真端点; 其余 mock)
  http.get(`${BASE}/projects/:id/stats`, async ({ params }) => {
    await delay(80)
    return HttpResponse.json(statsForProject(params.id as string))
  }),

  // 本周待办
  http.get(`${BASE}/projects/:id/todos`, async ({ params }) => {
    await delay(100)
    // 仅 demo 项目返回 fixtures, 新建项目无待办
    const todos: TodoItem[] = params.id === 'proj-demo-001' ? fixtureTodos : []
    return HttpResponse.json(todos)
  }),
]
