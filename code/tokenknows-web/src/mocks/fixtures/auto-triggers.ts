/**
 * v0.4 Auto-Trigger MSW fixtures.
 *
 * 4 条预置规则 (与 backend app/services/auto_trigger/default_rules/*.json 对齐)
 * + 一组执行历史样本 (展示时间轴 + 不同 status)
 */

import type { TriggerExecution, TriggerRule } from '@/types/api'

const ISO_NOW = new Date().toISOString()
const isoOffset = (daysAgo: number, hour = 9): string =>
  new Date(Date.now() - daysAgo * 86400_000 + hour * 3600_000).toISOString()

export const fixtureTriggerRules: TriggerRule[] = [
  {
    id: 'rule-default-incident',
    project_id: null,
    name: 'Issue 含 incident label → 自动复盘',
    description:
      'GitHub Issue 创建且 labels 含 incident/outage/production-issue 时, 自动生成复盘草稿 (v0.4.1 事件触发上线)',
    priority: 100,
    mode: 'event',
    asset_type: 'incident',
    enabled: true,
    cooldown_seconds: 1800,
    daily_cap: 5,
    event_match: {
      event_type: 'github_issue_opened',
      label_any: ['incident', 'outage', 'production-issue'],
    },
    created_by: 'system',
    created_at: ISO_NOW,
    updated_at: ISO_NOW,
  },
  {
    id: 'rule-default-adr',
    project_id: null,
    name: 'PR 含 architecture-decision label → ADR',
    description:
      'GitHub PR merge 且 labels 含 architecture-decision 或 adr 时, 自动生成 ADR 草稿 (v0.4.1 事件触发上线)',
    priority: 85,
    mode: 'event',
    asset_type: 'adr',
    enabled: true,
    cooldown_seconds: 3600,
    daily_cap: 5,
    event_match: {
      event_type: 'github_pr_merged',
      label_any: ['architecture-decision', 'adr'],
    },
    created_by: 'system',
    created_at: ISO_NOW,
    updated_at: ISO_NOW,
  },
  {
    id: 'rule-default-book',
    project_id: null,
    name: '累积 50 章 approved → 自动书籍',
    description:
      '项目累积 50+ 个已审批章节且未生成过 book 时, 自动生成内部技术手册 (Q4 决策: 默认 enabled=false; 因 book token 用量大约周报 20 倍, 需 Owner 显式开启)',
    priority: 70,
    mode: 'threshold',
    asset_type: 'book',
    enabled: false,
    cooldown_seconds: 604800,
    daily_cap: 1,
    threshold_spec: {
      metric: 'approved_chapters_total',
      comparator: '>=',
      value: 50,
      and_not_exists_asset_of_type: 'book',
    },
    created_by: 'system',
    created_at: ISO_NOW,
    updated_at: ISO_NOW,
  },
  {
    id: 'rule-default-weekly',
    project_id: null,
    name: '周一 09:00 自动周报',
    description:
      '每周一上午 9 点自动生成上周周报草稿; 要求上周事件数 ≥ 30 (避免低活跃项目产空报)',
    priority: 50,
    mode: 'cron',
    asset_type: 'weekly_report',
    enabled: true,
    cooldown_seconds: 86400,
    daily_cap: 1,
    cron_expr: '0 9 * * 1',
    extra_condition: {
      metric: 'events_last_7d',
      comparator: '>=',
      value: 30,
    },
    created_by: 'system',
    created_at: ISO_NOW,
    updated_at: ISO_NOW,
  },
]

export const fixtureTriggerExecutions: TriggerExecution[] = [
  {
    id: 'exec-mock-1',
    rule_id: 'rule-default-weekly',
    project_id: 'proj-demo-001',
    status: 'fired',
    fire_at: isoOffset(1, 9),
    fired_at: isoOffset(1, 9),
    signal: {
      type: 'cron',
      summary: '周一 09:00 cron 触发',
      payload: { cron_expr: '0 9 * * 1' },
    },
    evaluation: {
      matched: true,
      confidence: 1.0,
      notes: 'events_last_7d=87 ≥ 30',
    },
    asset_id: 'asset-9f2a5d0603',
    user_canceled: false,
    user_flagged_false_positive: false,
    created_at: isoOffset(1, 9),
  },
  {
    id: 'exec-mock-2',
    rule_id: 'rule-default-weekly',
    project_id: 'proj-demo-001',
    status: 'skipped',
    skip_reason: 'cooldown',
    fire_at: isoOffset(1, 10),
    signal: {
      type: 'cron',
      summary: '周一 10:00 cron (重复触发)',
    },
    evaluation: {
      matched: true,
      confidence: 1.0,
      notes: '距上次 fired < 86400s',
    },
    user_canceled: false,
    user_flagged_false_positive: false,
    created_at: isoOffset(1, 10),
  },
  {
    id: 'exec-mock-3',
    rule_id: 'rule-default-incident',
    project_id: 'proj-demo-001',
    status: 'fired',
    fire_at: isoOffset(3, 14),
    fired_at: isoOffset(3, 14),
    signal: {
      type: 'github_webhook',
      event_id: 'issue_opened_88',
      summary: 'Issue #88 · Bug: login fails (label incident)',
    },
    asset_id: 'asset-incident-mock',
    user_canceled: false,
    user_flagged_false_positive: false,
    created_at: isoOffset(3, 14),
  },
]
