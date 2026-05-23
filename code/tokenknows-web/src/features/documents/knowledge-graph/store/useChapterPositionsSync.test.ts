/**
 * useChapterPositionsSync · v1.3 T91 单测.
 *
 * 验:
 *   - 500ms debounce: 快速连续 sync 只发一次 PATCH (最后值)
 *   - PATCH body / URL 正确
 *   - assetId 或 chapterId 缺失 → 不发请求 (no-op)
 *   - 失败仅 console.warn, 不抛
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChapterPositionsSync } from './useChapterPositionsSync'

// Mock api client
const patchMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()
vi.mock('@/lib/api', () => ({
  api: {
    patch: (...args: unknown[]) => patchMock(...args),
  },
  isApiError: (e: unknown) => typeof e === 'object' && e !== null && 'code' in e,
}))

beforeEach(() => {
  vi.useFakeTimers()
  patchMock.mockReset()
  patchMock.mockResolvedValue({ data: {} })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useChapterPositionsSync', () => {
  it('单次 sync 触发 PATCH (500ms 后)', async () => {
    const { result } = renderHook(() => useChapterPositionsSync('a-1', 'ch-1'))
    act(() => {
      result.current.sync({ n_a: { x: 10, y: 20 } })
    })
    expect(patchMock).not.toHaveBeenCalled()
    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
    })
    expect(patchMock).toHaveBeenCalledTimes(1)
    const [url, body] = patchMock.mock.calls[0]
    expect(url).toBe('/assets/a-1/chapters/ch-1/positions')
    expect(body).toEqual({ positions: { n_a: { x: 10, y: 20 } } })
  })

  it('debounce: 快速连续 sync 只发最后一次', async () => {
    const { result } = renderHook(() => useChapterPositionsSync('a-1', 'ch-1'))
    act(() => {
      result.current.sync({ n_a: { x: 1, y: 1 } })
    })
    act(() => {
      vi.advanceTimersByTime(200)
      result.current.sync({ n_a: { x: 2, y: 2 } })
    })
    act(() => {
      vi.advanceTimersByTime(200)
      result.current.sync({ n_a: { x: 3, y: 3 } })
    })
    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
    })
    expect(patchMock).toHaveBeenCalledTimes(1)
    expect(patchMock.mock.calls[0][1]).toEqual({
      positions: { n_a: { x: 3, y: 3 } },
    })
  })

  it('assetId 为 null 时不发请求', async () => {
    const { result } = renderHook(() =>
      useChapterPositionsSync(null, 'ch-1'),
    )
    act(() => {
      result.current.sync({ n: { x: 1, y: 1 } })
    })
    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(patchMock).not.toHaveBeenCalled()
  })

  it('chapterId 为 null 时不发请求', async () => {
    const { result } = renderHook(() =>
      useChapterPositionsSync('a-1', null),
    )
    act(() => {
      result.current.sync({ n: { x: 1, y: 1 } })
    })
    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(patchMock).not.toHaveBeenCalled()
  })

  it('PATCH 失败仅 console.warn 不抛', async () => {
    patchMock.mockRejectedValueOnce({ code: 'SERVER_ERROR', message: 'down' })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { result } = renderHook(() => useChapterPositionsSync('a-1', 'ch-1'))
    act(() => {
      result.current.sync({ n: { x: 1, y: 1 } })
    })
    await act(async () => {
      vi.advanceTimersByTime(500)
      // 让 rejected promise 走完
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('卸载时清掉 pending debounce, 不再发请求', async () => {
    const { result, unmount } = renderHook(() =>
      useChapterPositionsSync('a-1', 'ch-1'),
    )
    act(() => {
      result.current.sync({ n: { x: 1, y: 1 } })
    })
    unmount()
    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(patchMock).not.toHaveBeenCalled()
  })
})
