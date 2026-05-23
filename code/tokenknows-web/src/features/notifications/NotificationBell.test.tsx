/**
 * NotificationBell · v0.5.1 T51 unit tests.
 *
 * 注: Radix DropdownMenu 在 jsdom 中难展开 (需 pointer events + portal),
 * 这里只测 bell button + badge 逻辑;
 * popover 内容 (NotificationList) 已单独测试 (见 NotificationList.test.tsx).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { NotificationBell } from './NotificationBell'

const mock = new MockAdapter(api)

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
    },
    accessToken: 'fake',
    isAuthenticated: true,
  })
}

beforeEach(() => {
  mock.reset()
  _setUser('ou-alice')
  // EventSource not in jsdom; stub to noop
  // @ts-expect-error
  globalThis.EventSource = class {
    addEventListener() {}
    close() {}
  }
})

afterEach(() => {
  // @ts-expect-error
  delete globalThis.EventSource
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
})

describe('NotificationBell', () => {
  it('未读 0 → 不显示 badge', async () => {
    mock.onGet('/me/notifications/unread-count').reply(200, { unread_count: 0 })
    mock.onGet(/\/me\/notifications/).reply(200, {
      items: [],
      unread_count: 0,
    })
    _render(<NotificationBell />)
    const bell = await screen.findByTestId('notification-bell')
    expect(bell).toBeInTheDocument()
    expect(screen.queryByTestId('notification-bell-badge')).toBeNull()
  })

  it('未读 5 → badge 显示 "5"', async () => {
    mock.onGet('/me/notifications/unread-count').reply(200, { unread_count: 5 })
    mock.onGet(/\/me\/notifications/).reply(200, { items: [], unread_count: 5 })
    _render(<NotificationBell />)
    const badge = await screen.findByTestId('notification-bell-badge')
    expect(badge.textContent).toBe('5')
  })

  it('未读 > 99 → badge "99+"', async () => {
    mock.onGet('/me/notifications/unread-count').reply(200, { unread_count: 150 })
    mock.onGet(/\/me\/notifications/).reply(200, {
      items: [],
      unread_count: 150,
    })
    _render(<NotificationBell />)
    const badge = await screen.findByTestId('notification-bell-badge')
    expect(badge.textContent).toBe('99+')
  })

  it('aria-label 含未读数', async () => {
    mock.onGet('/me/notifications/unread-count').reply(200, { unread_count: 3 })
    mock.onGet(/\/me\/notifications/).reply(200, { items: [], unread_count: 3 })
    _render(<NotificationBell />)
    await waitFor(() =>
      expect(screen.getByLabelText('通知 (3 未读)')).toBeInTheDocument(),
    )
  })
})
