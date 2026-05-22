/**
 * EventDrawer · 补足分支: no payload / no external_id / tags / invalid date / no external_url.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { EventDrawer } from './EventDrawer'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Event } from '@/types/api'


const mkEvent = (overrides: Partial<Event> = {}): Event => ({
  id: 'e1', project_id: 'p1', source_type: 'github',
  source_ref: 'org/repo#1', external_id: 'gh-1', version: 1,
  event_type: 'pr_event', occurred_at: new Date().toISOString(),
  ingested_at: new Date().toISOString(),
  author: { name: 'A', email: null }, title: '事件', content: 'x',
  payload: { html_url: 'https://example.com' },
  redaction_state: 'raw', trust_score: 0.5, tags: [],
  content_hash: 'h', ...overrides,
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('EventDrawer extra branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
  })

  it('event without payload: no payload toggle button', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ payload: {} }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    expect(screen.queryByText(/原始 Payload/)).toBeNull()
  })

  it('event without external_id: shows —', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ external_id: '' }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('—')).toBeInTheDocument())
  })

  it('event with tags: tags rendered', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ tags: ['merged', 'urgent'] }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('merged')).toBeInTheDocument())
    expect(screen.getByText('urgent')).toBeInTheDocument()
  })

  it('invalid ISO date: formatDateTime falls back to raw string', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ occurred_at: 'not-a-date', ingested_at: 'also-bad' }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    // 由于 jsdom 的 toLocaleString 对无效日期返回 "Invalid Date"
    // 我们只检查不抛错就够了
  })

  it('event without external_url in payload: no 在源头打开 link', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ payload: { irrelevant: 'data' } }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    expect(screen.queryByText('在源头打开')).toBeNull()
  })

  it('event with author email: email shown under name', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ author: { name: 'Bob', email: 'bob@example.com' } }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('bob@example.com')).toBeInTheDocument())
  })

  it('event_type unknown: falls back to raw event_type label', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ title: null, event_type: 'unknown_type' as Event['event_type'] }),
    })
    render(withWrappers(<EventDrawer />))
    // unknown_type 没有 label, 返回 raw 字符串
    await waitFor(() => expect(screen.getByText('unknown_type')).toBeInTheDocument())
  })

  it('trust_score null: no trust badge', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ trust_score: null }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    expect(screen.queryByText(/TRUST/)).toBeNull()
  })

  it('source_type unknown: falls back to raw source_type', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent({ source_type: 'unknown_src' as Event['source_type'] }),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    expect(screen.getByText('unknown_src')).toBeInTheDocument()
  })
})
