/**
 * Projects MSW handlers · /api/v1/projects/*
 *
 * 设计依据:
 *   - TDD §6.1 端点
 *   - TaskTechDesign T02 关键决策(409 重名立即报错)
 *
 * 内存状态: 维护项目列表 + 数据源列表, T02 测试时持久。
 */

import { http, HttpResponse, delay } from 'msw'
import { fixtureProjects } from '../fixtures/projects'
import type { Datasource, DatasourceType, Project } from '@/types/api'

const BASE = '/api/v1'

// in-memory state
const projects: Project[] = [...fixtureProjects]
const datasourcesByProject = new Map<string, Datasource[]>([
  [
    'proj-demo-001',
    [
      {
        id: 'ds-001',
        project_id: 'proj-demo-001',
        type: 'github',
        name: 'TokenKnows/tokenknows',
        config: { repo: 'TokenKnows/tokenknows' },
        health: 'healthy',
        last_synced_at: '2026-05-20T10:00:00Z',
        created_at: '2026-05-19T10:00:00Z',
      },
      {
        id: 'ds-002',
        project_id: 'proj-demo-001',
        type: 'claude_code',
        name: 'John 的工作站',
        config: { install_id: 'install-abc-123' },
        health: 'healthy',
        last_synced_at: '2026-05-20T11:30:00Z',
        created_at: '2026-05-19T10:30:00Z',
      },
    ],
  ],
])

function genId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

function genConnectionToken(projectId: string): string {
  const random = Math.random().toString(36).slice(2, 18)
  const sig = Math.random().toString(36).slice(2, 14)
  return `${projectId}.${random}.${sig}`
}

const ERROR_MODE = new URLSearchParams(
  typeof window !== 'undefined' ? window.location.search : '',
).get('mock_error')

export const projectHandlers = [
  // 列表
  http.get(`${BASE}/projects`, async () => {
    await delay(120)
    if (ERROR_MODE === 'projects') {
      return HttpResponse.json(
        { code: 'SERVER_ERROR', detail: 'mocked 500' },
        { status: 500 },
      )
    }
    return HttpResponse.json(projects)
  }),

  // 详情
  http.get(`${BASE}/projects/:id`, async ({ params }) => {
    await delay(80)
    const p = projects.find((x) => x.id === params.id)
    if (!p) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '项目不存在' }, { status: 404 })
    }
    return HttpResponse.json(p)
  }),

  // 新建
  http.post(`${BASE}/projects`, async ({ request }) => {
    await delay(180)
    const body = (await request.json()) as { name: string; description?: string }
    if (!body.name?.trim()) {
      return HttpResponse.json(
        { code: 'VALIDATION_ERROR', detail: '项目名不能为空' },
        { status: 422 },
      )
    }
    // 409 重名检测 (用户输入"重复"或匹配已有)
    if (
      body.name.trim() === '重复' ||
      projects.some((p) => p.name.trim() === body.name.trim())
    ) {
      return HttpResponse.json(
        { code: 'CONFLICT', detail: `项目名"${body.name}"已存在` },
        { status: 409 },
      )
    }
    const now = new Date().toISOString()
    const newProject: Project = {
      id: genId('proj'),
      name: body.name.trim(),
      description: body.description?.trim() ?? null,
      owner_id: 'user-001',
      llm_egress_enabled: false,
      task_egress_config: {},
      custom_redaction_terms: [],
      brand_theme: {},
      created_at: now,
      updated_at: now,
      role: 'owner',
      health: 'healthy',
      stats: {
        events_this_week: 0,
        assets_pending_review: 0,
        datasources_total: 0,
        datasources_healthy: 0,
      },
    }
    projects.push(newProject)
    datasourcesByProject.set(newProject.id, [])
    return HttpResponse.json(newProject, { status: 201 })
  }),

  // 列数据源
  http.get(`${BASE}/projects/:id/datasources`, async ({ params }) => {
    await delay(80)
    const list = datasourcesByProject.get(params.id as string) ?? []
    return HttpResponse.json(list)
  }),

  // 加数据源 (插件类: claude_code/cursor/vscode 返回 connection_token; github 验 PAT)
  http.post(`${BASE}/projects/:id/datasources/:type`, async ({ params, request }) => {
    await delay(240)
    const projectId = params.id as string
    const type = params.type as DatasourceType

    const project = projects.find((p) => p.id === projectId)
    if (!project) {
      return HttpResponse.json({ code: 'NOT_FOUND', detail: '项目不存在' }, { status: 404 })
    }

    const body = (await request.json().catch(() => ({}))) as {
      name?: string
      pat?: string
      repos?: string[]
    }

    // GitHub: 验 PAT 格式
    if (type === 'github') {
      if (!body.pat || !body.pat.startsWith('ghp_')) {
        return HttpResponse.json(
          { code: 'VALIDATION_ERROR', detail: 'PAT 格式无效, 应以 ghp_ 开头' },
          { status: 422 },
        )
      }
    }

    const ds: Datasource = {
      id: genId('ds'),
      project_id: projectId,
      type,
      name: body.name ?? defaultDatasourceName(type),
      config:
        type === 'github'
          ? { repos: body.repos ?? [] }
          : { install_id: genId('install') },
      connection_token: ['claude_code', 'cursor', 'vscode'].includes(type)
        ? genConnectionToken(projectId)
        : undefined,
      health: 'healthy',
      last_synced_at: null,
      created_at: new Date().toISOString(),
    }
    const existing = datasourcesByProject.get(projectId) ?? []
    datasourcesByProject.set(projectId, [...existing, ds])
    // 更新项目统计
    if (project.stats) {
      project.stats.datasources_total += 1
      project.stats.datasources_healthy += 1
    }
    return HttpResponse.json(ds, { status: 201 })
  }),

  // 健康检查
  http.get(
    `${BASE}/projects/:id/datasources/:dsId/health`,
    async ({ params }) => {
      await delay(360)
      const list = datasourcesByProject.get(params.id as string) ?? []
      const ds = list.find((x) => x.id === params.dsId)
      if (!ds) {
        return HttpResponse.json(
          { code: 'NOT_FOUND', detail: '数据源不存在' },
          { status: 404 },
        )
      }
      return HttpResponse.json({ id: ds.id, health: ds.health, last_synced_at: ds.last_synced_at })
    },
  ),
]

function defaultDatasourceName(type: DatasourceType): string {
  switch (type) {
    case 'claude_code':
      return 'Claude Code 插件'
    case 'claude_cowork':
      return 'Claude Cowork 插件'
    case 'cursor':
      return 'Cursor 扩展'
    case 'vscode':
      return 'VS Code 扩展'
    case 'github':
      return 'GitHub 仓库'
    case 'local_file':
      return '本地文件上传'
    default:
      return '未命名数据源'
  }
}
