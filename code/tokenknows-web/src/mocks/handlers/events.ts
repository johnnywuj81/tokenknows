/**
 * Events / Stats / Todos handlers · 工作台数据 (T03)
 *
 * 设计依据:
 *   - TDD §6.1: GET /projects/:id/events?from&to + GET /projects/:id/stats + GET /projects/:id/todos
 *   - SharedFoundations §5.3: queryKey 表
 *   - TaskTechDesign T03: 30s polling, cursor 分页
 */

import { http, HttpResponse, delay } from 'msw'
import type { Event, EventSourceType, ProjectStats, TodoItem } from '@/types/api'
import { fixtureEvents } from '../fixtures/events'
import { fixtureTodos } from '../fixtures/todos'

const BASE = '/api/v1'

// 内存可变事件 - 后续 polling 模拟新事件出现
const events: Event[] = [...fixtureEvents]

// 简单内存 stats 派生
function statsForProject(projectId: string): ProjectStats {
  const projEvents = events.filter((e) => e.project_id === projectId)
  const now = Date.now()
  const weekAgo = now - 7 * 24 * 60 * 60 * 1000
  const eventsThisWeek = projEvents.filter(
    (e) => new Date(e.occurred_at).getTime() >= weekAgo,
  ).length
  return {
    events_this_week: eventsThisWeek,
    assets_pending_review: 2,
    datasources_total: 3,
    datasources_healthy: 3,
  }
}

const ERROR_MODE = new URLSearchParams(
  typeof window !== 'undefined' ? window.location.search : '',
).get('mock_error')

export const eventHandlers = [
  // 事件流(支持 source_type / author 筛选 + cursor 分页 + from/to)
  http.get(`${BASE}/projects/:id/events`, async ({ params, request }) => {
    await delay(150)
    if (ERROR_MODE === 'events') {
      return HttpResponse.json(
        { code: 'SERVER_ERROR', detail: 'mocked 500' },
        { status: 500 },
      )
    }
    const projectId = params.id as string
    const url = new URL(request.url)
    const sourceType = url.searchParams.get('source_type') as EventSourceType | null
    const author = url.searchParams.get('author')
    const cursor = url.searchParams.get('cursor')
    const limit = Number(url.searchParams.get('limit') ?? 20)

    let filtered = events.filter((e) => e.project_id === projectId)
    if (sourceType) filtered = filtered.filter((e) => e.source_type === sourceType)
    if (author) {
      filtered = filtered.filter(
        (e) => e.author?.name === author || e.author?.email === author,
      )
    }

    // cursor = 上一批末尾的 id
    let startIdx = 0
    if (cursor) {
      const idx = filtered.findIndex((e) => e.id === cursor)
      if (idx >= 0) startIdx = idx + 1
    }
    const slice = filtered.slice(startIdx, startIdx + limit)
    const nextCursor = startIdx + limit < filtered.length ? slice[slice.length - 1]?.id : null

    return HttpResponse.json({
      data: slice,
      meta: {
        total: filtered.length,
        cursor: nextCursor,
        has_more: nextCursor !== null,
      },
    })
  }),

  // 事件详情(T04 用,提前实现)
  http.get(`${BASE}/events/:id`, async ({ params }) => {
    await delay(80)
    const e = events.find((x) => x.id === params.id)
    if (!e) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '事件不存在' }, { status: 404 })
    }
    return HttpResponse.json(e)
  }),

  // 项目统计
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
