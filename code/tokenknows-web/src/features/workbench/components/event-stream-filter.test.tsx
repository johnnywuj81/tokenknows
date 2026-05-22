/**
 * EventStream · sourceType-filter empty state branch.
 *
 * 选中筛选 source_type 后, 列表为空 → "该来源近期没有事件" + "尝试切换其它来源" 描述.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '@/lib/api'


// Mock EventFilter to bypass Radix portal / pointer-event complications
vi.mock('./EventFilter', () => ({
  EventFilter: ({ onChange }: { sourceType: unknown; onChange: (s: string | null) => void }) => (
    <button type="button" onClick={() => onChange('cursor')} data-testid="mock-filter-cursor">
      mock-filter
    </button>
  ),
}))


const { EventStream } = await import('./EventStream')


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


describe('EventStream sourceType filter empty', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('select sourceType=cursor + 0 events → 该来源近期没有事件', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { data: [], meta: { total: 0, cursor: null, has_more: false } },
    })
    render(withWrappers(<EventStream projectId="p1" />))
    // 默认空 → 显示 "尚无事件流入"
    await waitFor(() => expect(screen.getByText('尚无事件流入')).toBeInTheDocument())

    // 通过 mock 的 EventFilter 触发 onChange('cursor')
    fireEvent.click(screen.getByTestId('mock-filter-cursor'))

    // 选中后, sourceType !== null → 触发 line 81 + 84 branch
    await waitFor(() => expect(screen.getByText('该来源近期没有事件')).toBeInTheDocument())
    expect(screen.getByText(/尝试切换其它来源/)).toBeInTheDocument()
  })
})
