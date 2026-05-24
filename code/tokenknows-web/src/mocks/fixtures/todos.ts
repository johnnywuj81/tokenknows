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

// v1.8 修: asset_id 指向真存在的 demo asset, title 与 asset.title 匹配
// 真 backend asset (T127 后统一 proj-demo-001):
//   demo-kg-001 → '2026 Q2 Gateway 故障复盘 (Demo · proj-demo-001)' [knowledge_graph]
//   demo-wr-001 → '2026 Q2 W21 周报 (Demo · proj-demo-001)' [weekly_report]
export const fixtureTodos: TodoItem[] = [
  {
    id: 'todo-001',
    type: 'pending_review',
    title: '审批: Gateway 故障复盘 (知识图谱)',
    asset_id: 'demo-kg-001',
    due_at: isoOffset(-1, 18), // 已过期
    created_at: isoOffset(-3, 10),
  },
  {
    id: 'todo-002',
    type: 'pending_redaction',
    title: '脱敏确认: 2026 Q2 W21 周报',
    asset_id: 'demo-wr-001',
    due_at: isoOffset(0, 18),
    created_at: isoOffset(-1, 9),
  },
  {
    id: 'todo-003',
    type: 'pending_generate',
    title: '待生成: 本周技术方案 (无 asset_id, 点击跳列表)',
    // 无 asset_id → 点击 fallback 跳文档列表 (不 404)
    due_at: isoOffset(1, 18),
    created_at: isoOffset(-1, 14),
  },
  {
    id: 'todo-004',
    type: 'pending_publish',
    title: '发布: Gateway 故障复盘 (知识图谱)',
    asset_id: 'demo-kg-001',
    due_at: isoOffset(2, 18),
    created_at: isoOffset(-2, 11),
  },
  {
    id: 'todo-005',
    type: 'pending_review',
    title: '审批: 2026 Q2 W21 周报',
    asset_id: 'demo-wr-001',
    due_at: isoOffset(3, 18),
    created_at: isoOffset(-2, 15),
  },
  // T128/T134 demo: 章节被退回需要作者修订. 现实里这条由 backend
  // todo_service 从 asset.approval_state='rejected' 推导, 这里 fixture
  // 模拟它的样子, 让 dev mode 也能预览红点/banner 效果.
  {
    id: 'todo-006',
    type: 'pending_revision',
    title: '修订: 2026 Q2 W21 周报 (审批人退回了 §4 风险与阻塞)',
    asset_id: 'demo-wr-001',
    due_at: isoOffset(1, 18),
    created_at: isoOffset(0, 10),
  },
]
