/**
 * Mock fixtures · 文档资产
 *
 * 覆盖 4 类型 × 多状态以验证 DocumentCard 视觉。
 */

import type { Asset } from '@/types/api'

function isoOffset(daysAgo: number, hour = 10, minute = 0): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  d.setHours(hour, minute, 0, 0)
  return d.toISOString()
}

const PROJECT_ID = 'proj-demo-001'
const CREATOR = 'user-001'

export const fixtureAssets: Asset[] = [
  {
    id: 'asset-w21',
    project_id: PROJECT_ID,
    type: 'weekly_report',
    title: '周报 · Week 21 (2026-05-18 → 2026-05-21)',
    status: 'draft',
    current_version: 1,
    template_id: 'tpl-weekly',
    created_by: CREATOR,
    approval_state: 'pending',
    redaction_state: 'any_unresolved',
    metrics: { coverage: 0.78, citation_density: 0.65, slop_score: 0.18, similarity: 0.42 },
    created_at: isoOffset(0, 9, 12),
    updated_at: isoOffset(0, 9, 30),
  },
  {
    id: 'asset-w20',
    project_id: PROJECT_ID,
    type: 'weekly_report',
    title: '周报 · Week 20',
    status: 'in_review',
    current_version: 1,
    template_id: 'tpl-weekly',
    created_by: CREATOR,
    approval_state: 'pending',
    redaction_state: 'any_unresolved',
    metrics: { coverage: 0.84, citation_density: 0.72, slop_score: 0.12, similarity: 0.38 },
    created_at: isoOffset(7, 9, 0),
    updated_at: isoOffset(2, 14, 22),
  },
  {
    id: 'asset-43',
    project_id: PROJECT_ID,
    type: 'tech_design',
    title: 'T02 项目创建向导 · 技术方案',
    status: 'in_review',
    current_version: 1,
    template_id: 'tpl-tech-design',
    created_by: CREATOR,
    approval_state: 'pending',
    redaction_state: 'all_confirmed',
    metrics: { coverage: 0.91, citation_density: 0.81, slop_score: 0.08, similarity: 0.22 },
    created_at: isoOffset(3, 11, 0),
    updated_at: isoOffset(1, 15, 45),
  },
  {
    id: 'asset-adr-04',
    project_id: PROJECT_ID,
    type: 'adr',
    title: 'ADR-004 · LLM Gateway 三层出域门禁',
    status: 'approved',
    current_version: 2,
    template_id: 'tpl-adr',
    created_by: CREATOR,
    approval_state: 'approved',
    redaction_state: 'all_confirmed',
    metrics: { coverage: 0.96, citation_density: 0.88, slop_score: 0.05, similarity: 0.15 },
    created_at: isoOffset(5, 10, 0),
    updated_at: isoOffset(3, 16, 30),
  },
  {
    id: 'asset-adr-03',
    project_id: PROJECT_ID,
    type: 'adr',
    title: 'ADR-003 · 选 Postgres + pgvector 而非 ES',
    status: 'published',
    current_version: 1,
    template_id: 'tpl-adr',
    created_by: CREATOR,
    approval_state: 'approved',
    redaction_state: 'all_confirmed',
    metrics: { coverage: 0.94, citation_density: 0.79, slop_score: 0.06, similarity: 0.18 },
    created_at: isoOffset(14, 10, 0),
    updated_at: isoOffset(10, 17, 0),
  },
  {
    id: 'asset-pg-spike',
    project_id: PROJECT_ID,
    type: 'incident',
    title: '问题复盘 · pgvector 在 1M 行性能 spike',
    status: 'draft',
    current_version: 1,
    template_id: 'tpl-incident',
    created_by: CREATOR,
    approval_state: 'pending',
    redaction_state: 'any_unresolved',
    metrics: { coverage: 0.71, citation_density: 0.58, slop_score: 0.22, similarity: 0.5 },
    created_at: isoOffset(1, 13, 0),
    updated_at: isoOffset(0, 8, 45),
  },
  {
    id: 'asset-incident-sse',
    project_id: PROJECT_ID,
    type: 'incident',
    title: '问题复盘 · SSE 在 Safari 长连断开',
    status: 'archived',
    current_version: 1,
    template_id: 'tpl-incident',
    created_by: CREATOR,
    approval_state: 'approved',
    redaction_state: 'all_confirmed',
    metrics: { coverage: 0.82, citation_density: 0.66, slop_score: 0.14, similarity: 0.3 },
    created_at: isoOffset(20, 10, 0),
    updated_at: isoOffset(18, 11, 0),
  },
]
