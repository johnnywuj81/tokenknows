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

export const fixtureTodos: TodoItem[] = [
  {
    id: 'todo-001',
    type: 'pending_review',
    title: '审批: PR #43 · T02 项目创建向导',
    asset_id: 'asset-43',
    due_at: isoOffset(-1, 18), // 已过期
    created_at: isoOffset(-3, 10),
  },
  {
    id: 'todo-002',
    type: 'pending_redaction',
    title: '脱敏确认: 周报 Week 21 (3 处敏感项)',
    asset_id: 'asset-w21',
    due_at: isoOffset(0, 18),
    created_at: isoOffset(-1, 9),
  },
  {
    id: 'todo-003',
    type: 'pending_generate',
    title: '本周技术方案 ADR-005 等待生成',
    due_at: isoOffset(1, 18),
    created_at: isoOffset(-1, 14),
  },
  {
    id: 'todo-004',
    type: 'pending_publish',
    title: '发布: 复盘报告 - pgvector 性能 spike',
    asset_id: 'asset-pg-spike',
    due_at: isoOffset(2, 18),
    created_at: isoOffset(-2, 11),
  },
  {
    id: 'todo-005',
    type: 'pending_review',
    title: '审批: 周报草稿 Week 20',
    asset_id: 'asset-w20',
    due_at: isoOffset(3, 18),
    created_at: isoOffset(-2, 15),
  },
]
