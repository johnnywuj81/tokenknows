/**
 * MembersPanel · v0.9.0 T67 unit tests.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { MembersPanel } from './MembersPanel'

const mock = new MockAdapter(api)

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function _setUser(id: string) {
  useAuthStore.setState({
    user: {
      id,
      email: `${id}@x`,
      display_name: id,
      is_instance_admin: false,
      email_verified_at: null,
      created_at: '',
      updated_at: '',
    },
    accessToken: 'fake',
    isAuthenticated: true,
  })
}

beforeEach(() => {
  mock.reset()
})

afterEach(() => {
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
})

describe('MembersPanel', () => {
  it('empty project → bootstrap CTA 显示', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [],
      owner_count: 0,
      reviewer_count: 0,
      contributor_count: 0,
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('members-bootstrap')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('bootstrap-owner-btn')).toBeInTheDocument()
  })

  it('成员列表渲染 + role badge', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [
        {
          id: 'm-1',
          project_id: 'p-1',
          user_id: 'ou-alice',
          role: 'owner',
          added_by: 'ou-alice',
          added_at: '2026-01-01T00:00:00Z',
          note: null,
        },
        {
          id: 'm-2',
          project_id: 'p-1',
          user_id: 'ou-bob',
          role: 'reviewer',
          added_by: 'ou-alice',
          added_at: '2026-01-02T00:00:00Z',
          note: null,
        },
      ],
      owner_count: 1,
      reviewer_count: 1,
      contributor_count: 0,
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('members-table')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('member-row-ou-alice')).toBeInTheDocument()
    expect(screen.getByTestId('member-row-ou-bob')).toBeInTheDocument()
    // alice (owner) 看到 self 标记
    expect(screen.getByText(/\(你\)/)).toBeInTheDocument()
  })

  it('owner 可见 role select 和 add form', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [
        {
          id: 'm-1',
          project_id: 'p-1',
          user_id: 'ou-alice',
          role: 'owner',
          added_by: 'ou-alice',
          added_at: '2026-01-01',
          note: null,
        },
      ],
      owner_count: 1,
      reviewer_count: 0,
      contributor_count: 0,
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('add-member-form')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('role-select-ou-alice')).toBeInTheDocument()
  })

  it('非 owner 不显示 role select / add form', async () => {
    _setUser('ou-bob')  // bob 是 reviewer
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [
        {
          id: 'm-1',
          project_id: 'p-1',
          user_id: 'ou-alice',
          role: 'owner',
          added_by: 'ou-alice',
          added_at: '2026-01-01',
          note: null,
        },
        {
          id: 'm-2',
          project_id: 'p-1',
          user_id: 'ou-bob',
          role: 'reviewer',
          added_by: 'ou-alice',
          added_at: '2026-01-02',
          note: null,
        },
      ],
      owner_count: 1,
      reviewer_count: 1,
      contributor_count: 0,
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('members-table')).toBeInTheDocument(),
    )
    // 无 add form / 无 role select
    expect(screen.queryByTestId('add-member-form')).toBeNull()
    expect(screen.queryByTestId('role-select-ou-alice')).toBeNull()
  })

  it('owner 点击 add member → POST', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [
        {
          id: 'm-1',
          project_id: 'p-1',
          user_id: 'ou-alice',
          role: 'owner',
          added_by: 'ou-alice',
          added_at: '2026-01-01',
          note: null,
        },
      ],
      owner_count: 1,
      reviewer_count: 0,
      contributor_count: 0,
    })
    mock.onPost('/projects/p-1/members').reply(201, {
      id: 'm-x',
      project_id: 'p-1',
      user_id: 'ou-new',
      role: 'contributor',
      added_by: 'ou-alice',
      added_at: '2026-01-03',
      note: null,
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('add-member-form')).toBeInTheDocument(),
    )
    fireEvent.change(screen.getByTestId('add-member-user-id'), {
      target: { value: 'ou-new' },
    })
    fireEvent.click(screen.getByTestId('add-member-submit'))
    await waitFor(() => expect(mock.history.post.length).toBe(1))
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.user_id).toBe('ou-new')
    expect(body.role).toBe('contributor')
  })

  it('owner 点击移除 → DELETE', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [
        {
          id: 'm-1',
          project_id: 'p-1',
          user_id: 'ou-alice',
          role: 'owner',
          added_by: 'ou-alice',
          added_at: '2026-01-01',
          note: null,
        },
        {
          id: 'm-2',
          project_id: 'p-1',
          user_id: 'ou-bob',
          role: 'contributor',
          added_by: 'ou-alice',
          added_at: '2026-01-02',
          note: null,
        },
      ],
      owner_count: 1,
      reviewer_count: 0,
      contributor_count: 1,
    })
    mock.onDelete('/projects/p-1/members/ou-bob').reply(204)
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('member-row-ou-bob')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('remove-ou-bob'))
    await waitFor(() => expect(mock.history.delete.length).toBe(1))
  })

  it('bootstrap 按钮 → POST', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(200, {
      project_id: 'p-1',
      items: [],
      owner_count: 0,
      reviewer_count: 0,
      contributor_count: 0,
    })
    mock.onPost('/projects/p-1/members').reply(201, {
      id: 'm-x',
      project_id: 'p-1',
      user_id: 'ou-alice',
      role: 'owner',
      added_by: 'ou-alice',
      added_at: '2026-01-03',
      note: '(auto-bootstrap owner)',
    })
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('bootstrap-owner-btn')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('bootstrap-owner-btn'))
    await waitFor(() => expect(mock.history.post.length).toBe(1))
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.user_id).toBe('ou-alice')
    expect(body.role).toBe('owner')
  })

  it('error 状态显示重试链接', async () => {
    _setUser('ou-alice')
    mock.onGet('/projects/p-1/members').reply(500)
    _render(<MembersPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByText(/加载成员失败/)).toBeInTheDocument(),
    )
  })
})
