/**
 * Mock fixtures · 项目种子数据。
 * T02 完成后用户会在此基础上追加新建项目。
 */

import type { Project } from '@/types/api'

export const fixtureProjects: Project[] = [
  {
    id: 'proj-demo-001',
    name: 'TokenKnows 自身研发',
    description: '内部 dogfooding 项目, 沉淀产品本身的研发过程。',
    owner_id: 'user-001',
    llm_egress_enabled: false,
    task_egress_config: {},
    custom_redaction_terms: [],
    brand_theme: {},
    created_at: '2026-05-19T10:00:00Z',
    updated_at: '2026-05-20T10:00:00Z',
    role: 'owner',
    health: 'healthy',
    stats: {
      events_this_week: 142,
      assets_pending_review: 2,
      datasources_total: 3,
      datasources_healthy: 3,
    },
  },
]
