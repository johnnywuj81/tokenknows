/**
 * EventDrawer formatDateTime catch branch · 模拟 toLocaleString 抛出.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { EventDrawer } from './EventDrawer'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Event } from '@/types/api'


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


const mkEvent = (occurred_at: string): Event => ({
  id: 'e1', project_id: 'p1', source_type: 'github',
  source_ref: 'org/repo#1', external_id: 'ext', version: 1,
  event_type: 'pr_event', occurred_at, ingested_at: occurred_at,
  author: { name: 'A', email: null }, title: '事件',
  content: 'x', payload: {}, redaction_state: 'raw',
  trust_score: null, tags: [], content_hash: 'h',
})


describe('EventDrawer formatDateTime catch path', () => {
  let originalToLocale: typeof Date.prototype.toLocaleString

  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({ eventDrawerOpen: true, activeEventId: 'e1' })
    originalToLocale = Date.prototype.toLocaleString
    // mock toLocaleString to throw → 触发 EventDrawer formatDateTime 的 catch 分支
    Date.prototype.toLocaleString = vi.fn(() => {
      throw new Error('boom locale')
    }) as unknown as typeof Date.prototype.toLocaleString
  })

  afterEach(() => {
    Date.prototype.toLocaleString = originalToLocale
  })

  it('toLocaleString throws → falls back to raw iso string', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkEvent('2026-01-15T10:00:00Z'),
    })
    render(withWrappers(<EventDrawer />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    // Falls back: shows iso string directly
    expect(screen.getAllByText(/2026-01-15T10:00:00Z/).length).toBeGreaterThan(0)
  })
})
