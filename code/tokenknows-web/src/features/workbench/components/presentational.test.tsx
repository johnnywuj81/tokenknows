/**
 * Workbench presentational components 批测.
 *
 * EmptyWorkbench (with router) / EventFilter / EventCard / ProjectStats / TodoList
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { EmptyWorkbench } from './EmptyWorkbench'
import { EventFilter } from './EventFilter'
import { EventCard } from './EventCard'
import { ProjectStats } from './ProjectStats'
import { TodoList } from './TodoList'
import type {
  Event, EventSourceType, EventType, Project, ProjectStats as Stats,
  TodoItem,
} from '@/types/api'


// ─── EmptyWorkbench ──────────────────────────────────────────────


describe('EmptyWorkbench', () => {
  it('renders title + 2 feature cards', () => {
    render(
      <MemoryRouter>
        <EmptyWorkbench />
      </MemoryRouter>,
    )
    expect(screen.getByText(/建立你的研发知识空间/)).toBeInTheDocument()
    expect(screen.getByText('多源同步')).toBeInTheDocument()
    expect(screen.getByText('默认零出域')).toBeInTheDocument()
  })

  it('CTA button exists', () => {
    render(
      <MemoryRouter>
        <EmptyWorkbench />
      </MemoryRouter>,
    )
    const btn = screen.getByRole('button', { name: /新建项目/ })
    expect(btn).toBeInTheDocument()
  })
})


// ─── EventFilter ─────────────────────────────────────────────────


describe('EventFilter', () => {
  it('shows 全部来源 when sourceType null', () => {
    render(<EventFilter sourceType={null} onChange={() => {}} />)
    expect(screen.getByText(/全部来源/)).toBeInTheDocument()
  })

  it('shows label of selected source', () => {
    render(<EventFilter sourceType="github" onChange={() => {}} />)
    expect(screen.getByText(/GitHub/)).toBeInTheDocument()
  })

  it('shows Claude Code label when selected', () => {
    render(<EventFilter sourceType="claude_code" onChange={() => {}} />)
    expect(screen.getByText(/Claude Code/)).toBeInTheDocument()
  })
})


// ─── ProjectStats ────────────────────────────────────────────────


const mockProject: Project = {
  id: 'p1', name: '测试项目', description: '描述',
  owner_id: 'u1', llm_egress_enabled: false,
  task_egress_config: {},
  custom_redaction_terms: [], brand_theme: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  role: 'owner', health: 'healthy',
}


describe('ProjectStats', () => {
  it('renders 4 stat cards + project name', () => {
    const stats: Stats = {
      events_this_week: 100, assets_pending_review: 5,
      datasources_total: 3, datasources_healthy: 3,
    }
    render(<ProjectStats project={mockProject} stats={stats} isLoading={false} />)
    expect(screen.getByText('测试项目')).toBeInTheDocument()
    expect(screen.getByText('本周事件')).toBeInTheDocument()
    expect(screen.getByText('待审文档')).toBeInTheDocument()
  })

  it('loading state renders skeletons', () => {
    const { container } = render(
      <ProjectStats project={mockProject} stats={undefined} isLoading={true} />,
    )
    // 应该有 skeleton 占位 (animate-pulse)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('health degraded shows correct dot color', () => {
    render(
      <ProjectStats
        project={{ ...mockProject, health: 'degraded' }}
        stats={undefined}
        isLoading={false}
      />,
    )
    // 找带 aria-label 项目健康的元素
    const elt = screen.getByLabelText(/项目健康.*degraded/)
    expect(elt).toBeInTheDocument()
  })
})


// ─── TodoList ────────────────────────────────────────────────────


const mockTodos: TodoItem[] = [
  {
    id: 't1', type: 'pending_review',
    title: 'PR #42 待审',
    due_at: new Date(Date.now() + 86400000).toISOString(),
    created_at: new Date().toISOString(),
    asset_id: 'a1',
  },
  {
    id: 't2', type: 'pending_publish',
    title: '周报 W21 待发布',
    due_at: null,
    created_at: new Date().toISOString(),
    asset_id: 'a2',
  },
]


describe('TodoList', () => {
  it('renders todos list', () => {
    render(
      <MemoryRouter>
        <TodoList projectId="p1" todos={mockTodos} isLoading={false} error={null} onRetry={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/PR #42 待审/)).toBeInTheDocument()
    expect(screen.getByText(/周报 W21 待发布/)).toBeInTheDocument()
  })

  it('shows empty state when no todos', () => {
    render(
      <MemoryRouter>
        <TodoList projectId="p1" todos={[]} isLoading={false} error={null} onRetry={() => {}} />
      </MemoryRouter>,
    )
    // 空列表应不显示任何 todo 标题
    expect(screen.queryByText(/PR #42/)).toBeNull()
  })

  it('shows error state with retry', () => {
    const onRetry = vi.fn()
    render(
      <MemoryRouter>
        <TodoList
          projectId="p1" todos={undefined}
          isLoading={false}
          error={new Error('boom')}
          onRetry={onRetry}
        />
      </MemoryRouter>,
    )
    const retry = screen.getByRole('button', { name: /重试/ })
    fireEvent.click(retry)
    expect(onRetry).toHaveBeenCalled()
  })
})


// ─── EventCard ───────────────────────────────────────────────────


const mockEvent: Event = {
  id: 'ev-1', project_id: 'p1', source_type: 'github',
  source_ref: 'owner/repo', external_id: 'pr-42',
  version: 1, event_type: 'pr_event',
  occurred_at: new Date().toISOString(),
  ingested_at: new Date().toISOString(),
  author: { name: 'alice', email: 'a@b' },
  title: 'PR #42 · Fix login',
  content: 'Long content here',
  payload: {},
  redaction_state: 'raw',
  trust_score: 0.85,
  tags: ['merged'],
  content_hash: 'h1',
}


describe('EventCard', () => {
  it('renders title + source', () => {
    render(<EventCard event={mockEvent} onClick={() => {}} />)
    expect(screen.getByText(/PR #42/)).toBeInTheDocument()
  })

  it('onClick triggers callback on title click', () => {
    const onClick = vi.fn()
    render(<EventCard event={mockEvent} onClick={onClick} />)
    // 点 card 标题
    const title = screen.getByText(/PR #42/)
    fireEvent.click(title)
    expect(onClick).toHaveBeenCalled()
  })

  it('trust_score displayed as percentage', () => {
    render(<EventCard event={mockEvent} onClick={() => {}} />)
    expect(screen.getByText('85')).toBeInTheDocument()
  })
})
