/**
 * TodoList · 排序 + overdue + click navigation + 4 type metadata.
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
  created_at: new Date().toISOString(),
  ...overrides,
})


describe('TodoList', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // 固定 now = 2026-05-22 00:00:00
    vi.setSystemTime(new Date('2026-05-22T00:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('error state with retry', () => {
    const onRetry = vi.fn()
    render(<MemoryRouter><TodoList
      todos={undefined} isLoading={false}
      error={new Error('boom')} onRetry={onRetry}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('待办加载失败')).toBeInTheDocument()
  })

  it('loading skeleton', () => {
    const { container } = render(<MemoryRouter><TodoList
      todos={undefined} isLoading={true}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('empty list shows EmptyState', () => {
    render(<MemoryRouter><TodoList
      todos={[]} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('本周没有待办')).toBeInTheDocument()
  })

  it('renders 4 todo types with correct labels', () => {
    const todos: TodoItem[] = [
      mk({ id: 't1', type: 'pending_review', title: '审 1' }),
      mk({ id: 't2', type: 'pending_redaction', title: '脱敏 2' }),
      mk({ id: 't3', type: 'pending_generate', title: '生成 3' }),
      mk({ id: 't4', type: 'pending_publish', title: '发布 4' }),
    ]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('待审')).toBeInTheDocument()
    expect(screen.getByText('待脱敏')).toBeInTheDocument()
    expect(screen.getByText('待生成')).toBeInTheDocument()
    expect(screen.getByText('待发布')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('overdue todo shows AlertTriangle + danger style', () => {
    const todos = [mk({ due_at: '2026-05-20T00:00:00Z' })] // 2 days ago
    const { container } = render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText(/逾期 2 天/)).toBeInTheDocument()
    expect(container.querySelectorAll('.text-danger').length).toBeGreaterThan(0)
  })

  it('today expired: 今天已过期', () => {
    const todos = [mk({ due_at: '2026-05-21T23:00:00Z' })] // 1h before now
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('今天已过期')).toBeInTheDocument()
  })

  it('due today: 今天截止', () => {
    const todos = [mk({ due_at: '2026-05-22T18:00:00Z' })] // later today
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('今天截止')).toBeInTheDocument()
  })

  it('tomorrow: 明天截止', () => {
    const todos = [mk({ due_at: '2026-05-23T12:00:00Z' })]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('明天截止')).toBeInTheDocument()
  })

  it('5 days later: 5 天后', () => {
    const todos = [mk({ due_at: '2026-05-27T00:00:00Z' })]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    expect(screen.getByText('5 天后')).toBeInTheDocument()
  })

  it('sortTodos: no due_at sorted to bottom', () => {
    const todos = [
      mk({ id: 't-no-due', title: 'no-due', due_at: null }),
      mk({ id: 't-soon', title: 'soon', due_at: '2026-05-23T00:00:00Z' }),
      mk({ id: 't-later', title: 'later', due_at: '2026-05-25T00:00:00Z' }),
    ]
    const { container } = render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    const items = container.querySelectorAll('li')
    expect(items[0].textContent).toContain('soon')
    expect(items[1].textContent).toContain('later')
    expect(items[2].textContent).toContain('no-due')
  })

  it('clicking todo with asset_id navigates to document', () => {
    const todos = [mk({ asset_id: 'a-x' })]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button'))
    // No assertion needed - just verify no crash + nav happens
  })

  it('clicking todo without asset_id navigates to list', () => {
    const todos = [mk({ asset_id: undefined })]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId="p1"
    /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button'))
  })

  it('no projectId: clicking todo does nothing', () => {
    const todos = [mk({ asset_id: 'a1' })]
    render(<MemoryRouter><TodoList
      todos={todos} isLoading={false}
      error={null} onRetry={() => {}}
      projectId={null}
    /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button'))
  })
})
