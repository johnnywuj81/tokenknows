/**
 * Todos handler · 工作台 (T03)
 *
 * 已切换到真后端:
 *   - events / events/:id  (Claude Code + Cursor + GitHub 插件 → events 表)
 *   - projects/:id/stats   (events 表 + assets 内存索引 派生)
 *
 * 留 MSW mock:
 *   - todos  (todos 模型尚未做后端持久化, 留 fixture)
 */

import { http, HttpResponse, delay } from 'msw'
import type { TodoItem } from '@/types/api'
import { fixtureTodos } from '../fixtures/todos'

const BASE = '/api/v1'

export const eventHandlers = [
  // 本周待办 (仍 mock)
  http.get(`${BASE}/projects/:id/todos`, async ({ params }) => {
    await delay(100)
    const todos: TodoItem[] = params.id === 'proj-demo-001' ? fixtureTodos : []
    return HttpResponse.json(todos)
  }),
]
