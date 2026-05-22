/**
 * v0.4 Auto-Trigger MSW handlers · /api/v1/projects/:pid/auto-triggers/*
 *
 * 后端 T32 (REST API) 尚未实现, 前端先用 MSW 演示完整 UI 流程.
 * 后端 T32 上线后, 把这个 handler 从 handlers.ts 注册里移除即可切真后端.
 */

import { http, HttpResponse, delay } from 'msw'
import type { TriggerExecution, TriggerRule } from '@/types/api'
import {
  fixtureTriggerExecutions,
  fixtureTriggerRules,
} from '../fixtures/auto-triggers'

const BASE = '/api/v1'

// 可变内存状态 (启停 / 撤回历史在 session 内可变更)
const rules: TriggerRule[] = fixtureTriggerRules.map((r) => ({ ...r }))
const executions: TriggerExecution[] = fixtureTriggerExecutions.map((e) => ({ ...e }))

function findRule(id: string): TriggerRule | undefined {
  return rules.find((r) => r.id === id)
}

export const autoTriggerHandlers = [
  // ── 列规则 ──────────────────────────────────────────
  http.get(`${BASE}/projects/:pid/auto-triggers/rules`, async ({ request }) => {
    await delay(120)
    const url = new URL(request.url)
    const enabled = url.searchParams.get('enabled')
    const mode = url.searchParams.get('mode')
    let filtered = [...rules]
    if (enabled === 'true') filtered = filtered.filter((r) => r.enabled)
    if (enabled === 'false') filtered = filtered.filter((r) => !r.enabled)
    if (mode) filtered = filtered.filter((r) => r.mode === mode)
    return HttpResponse.json({ data: filtered })
  }),

  // ── 单条规则详情 ────────────────────────────────────
  http.get(
    `${BASE}/projects/:pid/auto-triggers/rules/:rid`,
    async ({ params }) => {
      await delay(80)
      const rule = findRule(params.rid as string)
      if (!rule) {
        return HttpResponse.json(
          { code: 'NOT_FOUND', detail: 'rule not found' },
          { status: 404 },
        )
      }
      return HttpResponse.json(rule)
    },
  ),

  // ── 启停 / 改 priority / cooldown ──────────────────
  http.patch(
    `${BASE}/projects/:pid/auto-triggers/rules/:rid`,
    async ({ params, request }) => {
      await delay(150)
      const rule = findRule(params.rid as string)
      if (!rule) {
        return HttpResponse.json(
          { code: 'NOT_FOUND', detail: 'rule not found' },
          { status: 404 },
        )
      }
      const body = (await request.json()) as Partial<TriggerRule>
      if (body.enabled !== undefined) rule.enabled = body.enabled
      if (body.priority !== undefined) rule.priority = body.priority
      if (body.cooldown_seconds !== undefined)
        rule.cooldown_seconds = body.cooldown_seconds
      if (body.daily_cap !== undefined) rule.daily_cap = body.daily_cap
      rule.updated_at = new Date().toISOString()
      return HttpResponse.json(rule)
    },
  ),

  // ── 执行历史 ──────────────────────────────────────
  http.get(
    `${BASE}/projects/:pid/auto-triggers/executions`,
    async ({ request, params }) => {
      await delay(120)
      const url = new URL(request.url)
      const ruleId = url.searchParams.get('rule_id')
      const status = url.searchParams.get('status')
      const limit = parseInt(url.searchParams.get('limit') ?? '50', 10)
      let filtered = executions.filter((e) => e.project_id === params.pid)
      if (ruleId) filtered = filtered.filter((e) => e.rule_id === ruleId)
      if (status) filtered = filtered.filter((e) => e.status === status)
      filtered.sort((a, b) => b.created_at.localeCompare(a.created_at))
      return HttpResponse.json({ data: filtered.slice(0, limit) })
    },
  ),

  // ── 取消 scheduled ────────────────────────────────
  http.post(
    `${BASE}/projects/:pid/auto-triggers/executions/:eid/cancel`,
    async ({ params }) => {
      await delay(100)
      const exec = executions.find((e) => e.id === params.eid)
      if (!exec) {
        return HttpResponse.json(
          { code: 'NOT_FOUND', detail: 'execution not found' },
          { status: 404 },
        )
      }
      if (exec.status !== 'scheduled') {
        return HttpResponse.json(
          { code: 'CONFLICT', detail: '仅 scheduled 状态可撤回' },
          { status: 409 },
        )
      }
      exec.status = 'canceled'
      exec.user_canceled = true
      return HttpResponse.json(exec)
    },
  ),

  // ── 误触发反馈 ────────────────────────────────────
  http.post(
    `${BASE}/projects/:pid/auto-triggers/executions/:eid/flag-false-positive`,
    async ({ params }) => {
      await delay(100)
      const exec = executions.find((e) => e.id === params.eid)
      if (!exec) {
        return HttpResponse.json(
          { code: 'NOT_FOUND', detail: 'execution not found' },
          { status: 404 },
        )
      }
      exec.user_flagged_false_positive = true
      return HttpResponse.json(exec)
    },
  ),

  // ── Onboarding (引导预览) ─────────────────────────
  http.get(`${BASE}/projects/:pid/auto-triggers/onboarding`, async () => {
    await delay(80)
    // 返回 4 条预置规则供用户在引导向导中勾选
    return HttpResponse.json({ default_rules: rules })
  }),

  // ── Onboarding 一键启用 ──────────────────────────
  http.post(
    `${BASE}/projects/:pid/auto-triggers/onboarding`,
    async ({ request }) => {
      await delay(200)
      const body = (await request.json()) as { enabled_rule_ids: string[] }
      const enabledIds = new Set(body.enabled_rule_ids)
      for (const r of rules) {
        if (enabledIds.has(r.id)) {
          r.enabled = true
        } else {
          r.enabled = false
        }
      }
      return HttpResponse.json({
        enabled_count: enabledIds.size,
        skipped_count: rules.length - enabledIds.size,
      })
    },
  ),
]
