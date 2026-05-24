/**
 * T134 · TodoList "新到"红点 badge + 全部已读按钮.
 *
 * 行为:
 *  - 首批 todos 挂载时全部进 baseline (没红点)
 *  - 后续 rerender 出现的新 todo IDs → 显示红点 + "N 新"计数
 *  - 点击新 todo → 自身红点消失, 但其他新 todo 保留
 *  - 点击"全部已读" → 所有红点消失
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TodoList } from './TodoList'
import type { TodoItem } from '@/types/api'


const mk = (overrides: Partial<TodoItem> = {}): TodoItem => ({
  id: 't1',
  type: 'pending_review',
  title: '审批文档',
  asset_id: 'a1',
  due_at: null,
  created_at: '2026-05-22T00:00:00Z',
  ...overrides,
})


describe('TodoList · T134 new-todo badge', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-22T00:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('首批 todos 全部入 baseline, 没有红点也没有 N 新 chip', () => {
    const todos = [mk({ id: 't1' }), mk({ id: 't2' })]
    render(
      <MemoryRouter>
        <TodoList
          todos={todos} isLoading={false} error={null}
          onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('todo-new-count')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t2')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-mark-all-seen')).not.toBeInTheDocument()
  })

  it('后续 rerender 新增 todo → 该 todo 出红点 + 头部 N 新 chip', () => {
    const initial = [mk({ id: 't1' })]
    const { rerender } = render(
      <MemoryRouter>
        <TodoList
          todos={initial} isLoading={false} error={null}
          onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('todo-new-count')).not.toBeInTheDocument()

    // 模拟 SSE/polling 后新增 t2
    rerender(
      <MemoryRouter>
        <TodoList
          todos={[mk({ id: 't1' }), mk({ id: 't2', title: '新到的待办' })]}
          isLoading={false} error={null} onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('todo-new-count')).toHaveTextContent('1 新')
    expect(screen.queryByTestId('todo-new-dot-t1')).not.toBeInTheDocument()
    expect(screen.getByTestId('todo-new-dot-t2')).toBeInTheDocument()
  })

  it('点击新 todo → 自身红点消失, 计数减一', () => {
    const initial = [mk({ id: 't1' })]
    const { rerender } = render(
      <MemoryRouter>
        <TodoList
          todos={initial} isLoading={false} error={null}
          onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    rerender(
      <MemoryRouter>
        <TodoList
          todos={[
            mk({ id: 't1' }),
            mk({ id: 't2', title: '新到 a' }),
            mk({ id: 't3', title: '新到 b' }),
          ]}
          isLoading={false} error={null} onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('todo-new-count')).toHaveTextContent('2 新')

    // 点击 t2 按钮 (实际是 navigate 触发, 测试里 MemoryRouter 吃下)
    fireEvent.click(screen.getByText('新到 a'))
    expect(screen.queryByTestId('todo-new-dot-t2')).not.toBeInTheDocument()
    // t3 仍然新
    expect(screen.getByTestId('todo-new-dot-t3')).toBeInTheDocument()
    expect(screen.getByTestId('todo-new-count')).toHaveTextContent('1 新')
  })

  it('点击"全部已读" → 所有红点消失, chip 也消失', () => {
    const { rerender } = render(
      <MemoryRouter>
        <TodoList
          todos={[mk({ id: 't1' })]} isLoading={false} error={null}
          onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    rerender(
      <MemoryRouter>
        <TodoList
          todos={[mk({ id: 't1' }), mk({ id: 't2' }), mk({ id: 't3' })]}
          isLoading={false} error={null} onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('todo-new-count')).toHaveTextContent('2 新')

    fireEvent.click(screen.getByTestId('todo-mark-all-seen'))
    expect(screen.queryByTestId('todo-new-count')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t2')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t3')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-mark-all-seen')).not.toBeInTheDocument()
  })

  it('isLoading=true → seenIds 不初始化, 后续 todos 第一次到也不算"新"', () => {
    const { rerender } = render(
      <MemoryRouter>
        <TodoList
          todos={undefined} isLoading={true} error={null}
          onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('todo-new-count')).not.toBeInTheDocument()

    // loading 结束 → todos 第一次到达 → 都入 baseline
    rerender(
      <MemoryRouter>
        <TodoList
          todos={[mk({ id: 't1' }), mk({ id: 't2' })]}
          isLoading={false} error={null} onRetry={() => {}} projectId="p1"
        />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('todo-new-count')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('todo-new-dot-t2')).not.toBeInTheDocument()
  })
})
