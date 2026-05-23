/**
 * NotificationList · v0.5.1 T51 unit tests.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { WebNotification } from '@/types/api'
import { NotificationList } from './NotificationList'

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

function _notif(id: string, overrides: Partial<WebNotification> = {}): WebNotification {
  return {
    id,
    user_id: 'ou-alice',
    type: 'consent_request',
    title: `title-${id}`,
    body: `body-${id}`,
    link_url: '/skills/x',
    read: false,
    created_at: new Date().toISOString(),
    related_skill_id: null,
    ...overrides,
  }
}

describe('NotificationList', () => {
  it('loading → 渲染 "加载中…"', () => {
    _render(<NotificationList notifications={[]} isLoading={true} />)
    expect(screen.getByText('加载中…')).toBeInTheDocument()
  })

  it('error → 渲染 error testid', () => {
    _render(<NotificationList notifications={[]} error="加载通知失败" />)
    expect(screen.getByTestId('notification-list-error')).toBeInTheDocument()
  })

  it('empty → 渲染 empty testid', () => {
    _render(<NotificationList notifications={[]} />)
    expect(screen.getByTestId('notification-list-empty')).toBeInTheDocument()
  })

  it('多条通知 → 全渲染', () => {
    const items = [_notif('a'), _notif('b'), _notif('c')]
    _render(<NotificationList notifications={items} />)
    expect(screen.getByTestId('notification-item-a')).toBeInTheDocument()
    expect(screen.getByTestId('notification-item-b')).toBeInTheDocument()
    expect(screen.getByTestId('notification-item-c')).toBeInTheDocument()
  })

  it('已读 item → opacity 60', () => {
    const items = [_notif('a', { read: true })]
    _render(<NotificationList notifications={items} />)
    const item = screen.getByTestId('notification-item-a')
    expect(item.getAttribute('data-read')).toBe('true')
    expect(item.className).toContain('opacity-60')
  })
})
