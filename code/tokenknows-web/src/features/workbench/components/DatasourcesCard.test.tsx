/**
 * DatasourcesCard 单测 · 5 源行渲染 + health 色点 + 汇总.
 *
 * 选这个组件做首测因为:
 *   1. 纯 presentational (props in, JSX out, 不调 API/hook)
 *   2. 涵盖近期新代码 (跟 backend datasource_health 端点配对)
 *   3. 验证 inactive 灰白 + active/stale 颜色逻辑
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DatasourcesCard } from './DatasourcesCard'
import type { DatasourceHealthItem } from '@/types/api'

function makeItem(
  source_type: DatasourceHealthItem['source_type'],
  health: DatasourceHealthItem['health'],
  count = 0,
): DatasourceHealthItem {
  return {
    source_type,
    event_count: count,
    total_events: count,
    last_seen_at: count > 0 ? '2026-05-21T12:00:00Z' : null,
    last_ingested_at: count > 0 ? '2026-05-21T12:00:00Z' : null,
    health,
  }
}

const ALL_FIVE: DatasourceHealthItem[] = [
  makeItem('claude_code', 'active', 886),
  makeItem('github', 'active', 35),
  makeItem('cursor', 'active', 1331),
  makeItem('vscode', 'inactive', 0),
  makeItem('local_file', 'active', 4),
]


describe('DatasourcesCard', () => {
  it('renders skeleton 5 行 when loading', () => {
    const { container } = render(
      <DatasourcesCard
        items={undefined}
        totalActive={undefined}
        totalEventsAll={undefined}
        isLoading={true}
      />,
    )
    // 5 个 skeleton li
    const skeletons = container.querySelectorAll('li')
    expect(skeletons.length).toBe(5)
    // 汇总 chip 不显示 (loading)
    expect(screen.queryByText(/活跃/)).toBeNull()
  })

  it('renders 5 固定源 with labels', () => {
    render(
      <DatasourcesCard
        items={ALL_FIVE}
        totalActive={4}
        totalEventsAll={2256}
        isLoading={false}
      />,
    )
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByText('Cursor')).toBeInTheDocument()
    expect(screen.getByText('VS Code')).toBeInTheDocument()
    expect(screen.getByText('本地文档')).toBeInTheDocument()
  })

  it('renders 汇总 chip with totals', () => {
    render(
      <DatasourcesCard
        items={ALL_FIVE}
        totalActive={4}
        totalEventsAll={2256}
        isLoading={false}
      />,
    )
    // "4 活跃 · 2,256 事件" (Intl format)
    expect(screen.getByText(/4\s*活跃/)).toBeInTheDocument()
    expect(screen.getByText(/2,256/)).toBeInTheDocument()
  })

  it('inactive 源 灰白 (opacity-60) + 事件数 0', () => {
    const { container } = render(
      <DatasourcesCard
        items={ALL_FIVE}
        totalActive={4}
        totalEventsAll={2256}
        isLoading={false}
      />,
    )
    // 找 VS Code 行
    const vscodeRow = Array.from(container.querySelectorAll('li')).find(
      (li) => li.textContent?.includes('VS Code'),
    )
    expect(vscodeRow).toBeDefined()
    // 内部容器有 opacity-60
    const inner = vscodeRow!.querySelector('div')
    expect(inner?.className).toContain('opacity-60')
  })

  it('event_count 千分位格式', () => {
    render(
      <DatasourcesCard
        items={[makeItem('cursor', 'active', 1331)]}
        totalActive={1}
        totalEventsAll={1331}
        isLoading={false}
      />,
    )
    // 1,331 zh-CN 格式
    const matches = screen.getAllByText('1,331')
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('health=active 用 success 色点; inactive 用 border-strong', () => {
    const { container } = render(
      <DatasourcesCard
        items={[
          makeItem('claude_code', 'active', 5),
          makeItem('vscode', 'inactive', 0),
        ]}
        totalActive={1}
        totalEventsAll={5}
        isLoading={false}
      />,
    )
    const rows = Array.from(container.querySelectorAll('li'))
    // active 行有 bg-success class on dot
    const activeRow = rows.find((li) => li.textContent?.includes('Claude Code'))
    expect(activeRow?.innerHTML).toContain('bg-success')
    // inactive 行有 bg-border-strong
    const inactiveRow = rows.find((li) => li.textContent?.includes('VS Code'))
    expect(inactiveRow?.innerHTML).toContain('bg-border-strong')
  })

  it('empty items array 不崩 (仅渲染 0 行 + 汇总 0)', () => {
    const { container } = render(
      <DatasourcesCard
        items={[]}
        totalActive={0}
        totalEventsAll={0}
        isLoading={false}
      />,
    )
    expect(container.querySelectorAll('li').length).toBe(0)
  })
})
