/**
 * Mock fixtures · 工作台本周待办
 */

import type { TodoItem } from '@/types/api'

function isoOffset(daysFromNow: number, hour = 18): string {
  const d = new Date()
  d.setDate(d.getDate() + daysFromNow)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}

// v1.8 修: asset_id 指向真存在的 demo asset (避免点进去 404)
// 真 backend 有 demo-kg-001 (KG) + demo-wr-001 (weekly_report) 兜底
export const fixtureTodos: TodoItem[] = [
  {
    id: 'todo-001',
    type: 'pending_review',
    title: '审批: 知识图谱 demo · Gateway 故障复盘',
    asset_id: 'demo-kg-001',
    due_at: isoOffset(-1, 18), // 已过期
    created_at: isoOffset(-3, 10),
  },
  {
    id: 'todo-002',
    type: 'pending_redaction',
    title: '脱敏确认: 周报 Week 21 demo',
    asset_id: 'demo-wr-001',
    due_at: isoOffset(0, 18),
    created_at: isoOffset(-1, 9),
  },
  {
    id: 'todo-003',
    type: 'pending_generate',
    title: '本周技术方案 ADR-005 等待生成',
    // 无 asset_id → 点击 fallback 跳文档列表 (不 404)
    due_at: isoOffset(1, 18),
    created_at: isoOffset(-1, 14),
  },
  {
    id: 'todo-004',
    type: 'pending_publish',
    title: '发布: 知识图谱 · 跨实体合并验证',
    asset_id: 'demo-kg-001',
    due_at: isoOffset(2, 18),
    created_at: isoOffset(-2, 11),
  },
  {
    id: 'todo-005',
    type: 'pending_review',
    title: '审批: 周报草稿 Week 20',
    asset_id: 'demo-wr-001',
    due_at: isoOffset(3, 18),
    created_at: isoOffset(-2, 15),
  },
]
