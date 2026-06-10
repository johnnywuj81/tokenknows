/**
 * DocumentPage · action callbacks (submit / retry / regenerate).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import DocumentPage from './DocumentPage'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'draft', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const mkChapter = (id: string, order: number): Chapter => ({
  id, asset_id: 'a1', asset_version: 1, order_index: order,
  title: `章节 ${order + 1}`, content: '内容', layout: {},
  generated_by: null, regeneration_history: [], approval_state: 'pending',
  redacted_spans: [],
  created_at: '', updated_at: '',
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId" element={ui} />
          <Route path="/projects/:id/documents/:docId/review" element={<div>REVIEW</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('DocumentPage action callbacks', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('提交审批 button → submit mutation + navigate to review', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter('c1', 0)] })
      return Promise.resolve({ data: mkAsset({ status: 'draft' }) })
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    render(withWrappers(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('提交审批')).toBeInTheDocument())
    fireEvent.click(screen.getByText('提交审批'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('REVIEW')).toBeInTheDocument())
  })

  it('error retry buttons work', async () => {
    let callCount = 0
    vi.spyOn(api, 'get').mockImplementation(() => {
      callCount += 1
      return Promise.reject(new Error('fail'))
    })
    render(withWrappers(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('文档加载失败')).toBeInTheDocument())
    const initial = callCount
    // retry button
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(callCount).toBeGreaterThan(initial))
  })

  it('approved status: 发布 button → opens PublishDialog (via store)', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter('c1', 0)] })
      return Promise.resolve({ data: mkAsset({ status: 'approved' }) })
    })
    render(withWrappers(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('发布')).toBeInTheDocument())
    fireEvent.click(screen.getByText('发布'))
    // PublishDialog opens
    await waitFor(() => expect(screen.getByText('发布文档')).toBeInTheDocument())
  })

  it('chapter footer 重生成 button → opens RegenerateDialog (via store)', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter('c1', 0)] })
      return Promise.resolve({ data: mkAsset({ status: 'draft' }) })
    })
    render(withWrappers(<DocumentPage />))
    await waitFor(() => expect(screen.getByText('重生成')).toBeInTheDocument())
    fireEvent.click(screen.getByText('重生成'))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
  })
})
