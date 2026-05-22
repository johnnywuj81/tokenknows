/**
 * Workbench hooks 单测 · TanStack Query + axios mock.
 *
 * useProject / useProjects / useProjectStats / useTodos / useEvent /
 * useDatasourceHealth / useEventStream
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useProject } from './useProject'
import { useProjects } from './useProjects'
import { useProjectStats } from './useProjectStats'
import { useTodos } from './useTodos'
import { useEvent } from './useEvent'
import { useDatasourceHealth } from './useDatasourceHealth'
import { useEventStream } from './useEventStream'
import { api } from '@/lib/api'


function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}


beforeEach(() => {
  vi.spyOn(api, 'get').mockResolvedValue({ data: {} } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})


describe('useProject', () => {
  it('disabled when id null', async () => {
    const { result } = renderHook(() => useProject(null), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('disabled when id undefined', async () => {
    const { result } = renderHook(() => useProject(undefined), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches when id provided', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: { id: 'p1', name: 'test' } } as never)
    const { result } = renderHook(() => useProject('p1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.id).toBe('p1')
    expect(api.get).toHaveBeenCalledWith('/projects/p1')
  })
})


describe('useProjects', () => {
  it('fetches list', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: [{ id: 'p1' }, { id: 'p2' }],   // useProjects returns Project[] directly
    } as never)
    const { result } = renderHook(() => useProjects(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(2)
  })
})


describe('useProjectStats', () => {
  it('disabled when id null', () => {
    const { result } = renderHook(() => useProjectStats(null), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches stats endpoint', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { events_this_week: 42, assets_pending_review: 1,
              datasources_total: 3, datasources_healthy: 3 },
    } as never)
    const { result } = renderHook(() => useProjectStats('p1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.events_this_week).toBe(42)
    expect(api.get).toHaveBeenCalledWith('/projects/p1/stats')
  })
})


describe('useTodos', () => {
  it('disabled when projectId null', () => {
    const { result } = renderHook(() => useTodos(null), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches todos for project', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { data: [] },
    } as never)
    const { result } = renderHook(() => useTodos('p1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })
})


describe('useEvent', () => {
  it('disabled when id null', () => {
    const { result } = renderHook(() => useEvent(null), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches event detail', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { id: 'ev-1', title: 'x' },
    } as never)
    const { result } = renderHook(() => useEvent('ev-1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith('/events/ev-1')
  })
})


describe('useDatasourceHealth', () => {
  it('disabled when projectId null', () => {
    const { result } = renderHook(() => useDatasourceHealth(null), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches health for project', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { items: [], window_days: 30, total_active: 0, total_events_window: 0, total_events_all: 0 },
    } as never)
    const { result } = renderHook(() => useDatasourceHealth('p1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.get).toHaveBeenCalledWith(
      '/projects/p1/datasources/health',
      expect.objectContaining({ params: expect.objectContaining({ window_days: 30 }) }),
    )
  })

  it('passes custom window_days', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { items: [], window_days: 7, total_active: 0, total_events_window: 0, total_events_all: 0 },
    } as never)
    renderHook(() => useDatasourceHealth('p1', 7), { wrapper: createWrapper() })
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/projects/p1/datasources/health',
        expect.objectContaining({ params: expect.objectContaining({ window_days: 7 }) }),
      )
    })
  })
})


describe('useEventStream', () => {
  it('disabled when projectId null', () => {
    const { result } = renderHook(
      () => useEventStream(null),
      { wrapper: createWrapper() },
    )
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches events with default filter', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    } as never)
    const { result } = renderHook(
      () => useEventStream('p1'),
      { wrapper: createWrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('passes source_type filter', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    } as never)
    renderHook(
      () => useEventStream('p1', { source_type: 'github' }),
      { wrapper: createWrapper() },
    )
    await waitFor(() => {
      expect(api.get).toHaveBeenCalled()
    })
  })
})
