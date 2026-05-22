/**
 * Projects hooks · useCreateProject + useAddDatasource.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useCreateProject } from './useCreateProject'
import { useAddDatasource } from './useAddDatasource'
import { api } from '@/lib/api'


function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


afterEach(() => {
  vi.restoreAllMocks()
})


describe('useCreateProject', () => {
  it('POST /projects', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'p1', name: 'New' },
    } as never)
    const { result } = renderHook(() => useCreateProject(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ name: 'New', description: 'desc' })
    })
    expect(postSpy).toHaveBeenCalledWith('/projects', { name: 'New', description: 'desc' })
  })
})


describe('useAddDatasource', () => {
  it('POST datasource with type in URL', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'ds1', type: 'github' },
    } as never)
    const { result } = renderHook(() => useAddDatasource(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({
        projectId: 'p1', type: 'github',
        body: { pat: 'ghp_xxx', repos: ['o/r'] },
      })
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/projects/p1/datasources/github',
      { pat: 'ghp_xxx', repos: ['o/r'] },
    )
  })

  it('POST without body uses empty object', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { id: 'ds2', type: 'claude_code' },
    } as never)
    const { result } = renderHook(() => useAddDatasource(), { wrapper: wrapper() })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 'p1', type: 'claude_code' })
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/projects/p1/datasources/claude_code',
      {},
    )
  })
})
