/**
 * Assets MSW handlers · /api/v1/projects/:id/assets/*
 *
 * 设计依据:
 *   - TDD §6.1
 *   - TaskTechDesign T05 / T06 关键决策
 *
 * 内存状态: assets 数组, generate 后 5s 自动转 draft (模拟生成完成)。
 */

import { http, HttpResponse, delay } from 'msw'
import type { Asset, AssetStatus, AssetType } from '@/types/api'
import { fixtureAssets } from '../fixtures/assets'

const BASE = '/api/v1'

const assets: Asset[] = [...fixtureAssets]

function genId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

const ERROR_MODE = new URLSearchParams(
  typeof window !== 'undefined' ? window.location.search : '',
).get('mock_error')

const TITLE_TEMPLATES: Record<AssetType, (window: string) => string> = {
  weekly_report: (w) => `周报 · ${w}`,
  tech_design: (w) => `技术方案 · ${w}`,
  adr: () => 'ADR · 新决策记录(待补主题)',
  incident: () => '问题复盘 · 新事件',
}

export const assetHandlers = [
  // 列表 (filter + cursor)
  http.get(`${BASE}/projects/:id/assets`, async ({ params, request }) => {
    await delay(150)
    if (ERROR_MODE === 'assets') {
      return HttpResponse.json(
        { code: 'SERVER_ERROR', detail: 'mocked 500' },
        { status: 500 },
      )
    }
    const projectId = params.id as string
    const url = new URL(request.url)
    const type = url.searchParams.get('type') as AssetType | null
    const status = url.searchParams.get('status') as AssetStatus | null
    const cursor = url.searchParams.get('cursor')
    const limit = Number(url.searchParams.get('limit') ?? 20)

    let filtered = assets.filter((a) => a.project_id === projectId)
    if (type) filtered = filtered.filter((a) => a.type === type)
    if (status) filtered = filtered.filter((a) => a.status === status)

    filtered = filtered.sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    )

    let startIdx = 0
    if (cursor) {
      const idx = filtered.findIndex((a) => a.id === cursor)
      if (idx >= 0) startIdx = idx + 1
    }
    const slice = filtered.slice(startIdx, startIdx + limit)
    const nextCursor =
      startIdx + limit < filtered.length ? slice[slice.length - 1]?.id : null

    return HttpResponse.json({
      data: slice,
      meta: { total: filtered.length, cursor: nextCursor, has_more: nextCursor !== null },
    })
  }),

  // 单文档详情(T06 用)
  http.get(`${BASE}/assets/:assetId`, async ({ params }) => {
    await delay(80)
    const a = assets.find((x) => x.id === params.assetId)
    if (!a) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '文档不存在' }, { status: 404 })
    }
    return HttpResponse.json(a)
  }),

  // 触发生成
  http.post(`${BASE}/projects/:id/assets/generate`, async ({ params, request }) => {
    await delay(200)
    const projectId = params.id as string
    const body = (await request.json().catch(() => ({}))) as {
      type?: AssetType
      time_window?: string
      model_override?: string
    }
    const type = (body.type ?? 'weekly_report') as AssetType
    const title = TITLE_TEMPLATES[type](body.time_window ?? '本周')
    const now = new Date().toISOString()
    const newAsset: Asset = {
      id: genId('asset'),
      project_id: projectId,
      type,
      title,
      status: 'generating',
      current_version: 0,
      template_id: `tpl-${type}`,
      created_by: 'user-001',
      approval_state: 'pending',
      redaction_state: 'any_unresolved',
      metrics: null,
      created_at: now,
      updated_at: now,
    }
    assets.unshift(newAsset)

    // 5s 后自动转 draft + 填充 metrics
    setTimeout(() => {
      const idx = assets.findIndex((a) => a.id === newAsset.id)
      if (idx >= 0) {
        assets[idx] = {
          ...assets[idx],
          status: 'draft',
          current_version: 1,
          updated_at: new Date().toISOString(),
          metrics: {
            coverage: 0.75 + Math.random() * 0.2,
            citation_density: 0.55 + Math.random() * 0.3,
            slop_score: Math.random() * 0.2,
            similarity: Math.random() * 0.4,
          },
        }
      }
    }, 5000)

    return HttpResponse.json(newAsset, { status: 202 })
  }),

  // 删除(软删 - 转 archived)
  http.delete(`${BASE}/assets/:assetId`, async ({ params }) => {
    await delay(150)
    const idx = assets.findIndex((a) => a.id === params.assetId)
    if (idx < 0) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '文档不存在' }, { status: 404 })
    }
    assets.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // 克隆(复制 asset → 新草稿)
  http.post(`${BASE}/assets/:assetId/clone`, async ({ params }) => {
    await delay(180)
    const src = assets.find((a) => a.id === params.assetId)
    if (!src) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '文档不存在' }, { status: 404 })
    }
    const now = new Date().toISOString()
    const cloned: Asset = {
      ...src,
      id: genId('asset'),
      title: `${src.title} (副本)`,
      status: 'draft',
      current_version: 1,
      approval_state: 'pending',
      redaction_state: 'any_unresolved',
      created_at: now,
      updated_at: now,
    }
    assets.unshift(cloned)
    return HttpResponse.json(cloned, { status: 201 })
  }),
]
