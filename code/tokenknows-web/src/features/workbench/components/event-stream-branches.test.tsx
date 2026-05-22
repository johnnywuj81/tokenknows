/**
 * EventStream 余下分支 · RefreshCw 刷新中 + sourceType 空状态 + 加载更早 spinner.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { EventStream } from './EventStream'
import { api } from '@/lib/api'
import type { Event } from '@/types/api'


const mkEvent = (overrides: Partial<Event> = {}): Event => ({
  id: 'e1', project_id: 'p1', source_type: 'github',
  source_ref: 'org/repo#1', external_id: 'ext', version: 1,
  event_type: 'pr_event', occurred_at: new Date().toISOString(),
  ingested_at: new Date().toISOString(),
  author: { name: 'A', email: null }, title: '事件',
  content: 'c', payload: {}, redaction_state: 'raw',
  trust_score: 0.5, tags: [], content_hash: 'h',
  ...overrides,
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


describe('EventStream remaining branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('refetch shows RefreshCw indicator (aria-label="刷新中")', async () => {
    let resolveSecond: ((v: unknown) => void) | null = null
    let callCount = 0
    vi.spyOn(api, 'get').mockImplementation(() => {
      callCount += 1
      if (callCount === 1) {
        return Promise.resolve({
          data: { data: [mkEvent()], meta: { total: 1, cursor: null, has_more: false } },
        })
      }
      return new Promise((res) => { resolveSecond = res })
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => expect(screen.getByText('事件')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('立即刷新'))
    await waitFor(() => expect(screen.getByLabelText('刷新中')).toBeInTheDocument())
    resolveSecond?.({
      data: { data: [mkEvent()], meta: { total: 1, cursor: null, has_more: false } },
    })
  })

  it('isFetchingNextPage: 加载中 spinner inside button', async () => {
    let callCount = 0
    let resolveSecond: ((v: unknown) => void) | null = null
    vi.spyOn(api, 'get').mockImplementation(() => {
      callCount += 1
      if (callCount === 1) {
        return Promise.resolve({
          data: { data: [mkEvent()], meta: { total: 99, cursor: 'next-cursor', has_more: true } },
        })
      }
      return new Promise((res) => { resolveSecond = res })
    })
    render(withWrappers(<EventStream projectId="p1" />))
    await waitFor(() => expect(screen.getByText('加载更早')).toBeInTheDocument())
    fireEvent.click(screen.getByText('加载更早'))
    await waitFor(() => expect(screen.getByText('加载中')).toBeInTheDocument())
    resolveSecond?.({
      data: { data: [], meta: { total: 99, cursor: null, has_more: false } },
    })
  })

  it('disabled projectId: query disabled, no events', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withWrappers(<EventStream projectId={null} />))
    // useEventStream enabled=false; allEvents empty; show EmptyState
    await waitFor(() => expect(screen.getByText('尚无事件流入')).toBeInTheDocument())
  })
})
