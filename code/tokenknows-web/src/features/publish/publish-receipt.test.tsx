/**
 * PublishReceiptPage · T12 publish receipt page.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import PublishReceiptPage from './PublishReceiptPage'
import { api } from '@/lib/api'
import type { PublishRecord, Asset, Chapter } from '@/types/api'


const mkRecord = (overrides: Partial<PublishRecord> = {}): PublishRecord => ({
  id: 'rec1',
  asset_id: 'a1',
  asset_version: 2,
  destination: 'internal',
  destination_ref: null,
  publish_mode: 'full',
  status: 'success',
  url: 'https://x.test/doc/abc',
  published_at: '2026-01-15T10:00:00Z',
  published_by: 'u1',
  visibility: null,
  error: null,
  ...overrides,
})

const mkAsset: Asset = {
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'published', current_version: 2, template_id: null, created_by: 'u1',
  approval_state: 'approved', redaction_state: 'all_confirmed', metrics: null,
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
}

const mkChapter: Chapter = {
  id: 'c1', asset_id: 'a1', asset_version: 2, order_index: 0,
  title: 'ch', content: 'new', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
}


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1/published/rec1']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId/published/:publishId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('PublishReceiptPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows loading skeleton while fetching record', () => {
    // never resolve to capture loading
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    const { container } = render(withWrappers(<PublishReceiptPage />))
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('shows error state on record load failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('加载发布记录失败')).toBeInTheDocument())
  })

  it('renders success header + version + destination card', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) return Promise.resolve({ data: mkRecord() })
      if (url.includes('/assets/a1/publish-records')) return Promise.resolve({ data: [mkRecord()] })
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [mkChapter] })
      if (url.endsWith('/assets/a1')) return Promise.resolve({ data: mkAsset })
      return Promise.resolve({ data: null })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('发布成功')).toBeInTheDocument())
    expect(screen.getByText('站内文档库')).toBeInTheDocument()
    expect(screen.getByText('https://x.test/doc/abc')).toBeInTheDocument()
  })

  it('copy button copies url + shows 已复制', async () => {
    const clipSpy = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText: clipSpy } })
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) return Promise.resolve({ data: mkRecord() })
      if (url.includes('/assets/a1/publish-records')) return Promise.resolve({ data: [mkRecord()] })
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('复制')).toBeInTheDocument())
    fireEvent.click(screen.getByText('复制'))
    await waitFor(() => {
      expect(clipSpy).toHaveBeenCalledWith('https://x.test/doc/abc')
      expect(screen.getByText('已复制')).toBeInTheDocument()
    })
  })

  it('renders history list when 2+ records', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) return Promise.resolve({ data: mkRecord() })
      if (url.includes('/assets/a1/publish-records')) {
        return Promise.resolve({
          data: [
            mkRecord(),
            mkRecord({ id: 'rec2', destination: 'public_link', url: 'https://x.test/p/2' }),
          ],
        })
      }
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('历史发布记录')).toBeInTheDocument())
    expect(screen.getByText('公开链接')).toBeInTheDocument()
  })

  it('shows 无 diff 历史 message when no chapters have regen', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) return Promise.resolve({ data: mkRecord() })
      if (url.includes('/assets/a1/publish-records')) return Promise.resolve({ data: [mkRecord()] })
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [mkChapter] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText(/未经重生成/)).toBeInTheDocument())
  })

  it('shows chapter diff when chapters have regen history', async () => {
    const chapterWithDiff: Chapter = {
      ...mkChapter,
      content: 'new content',
      regeneration_history: [{
        at: '2026-01-15T09:00:00Z',
        user_id: 'u1',
        instruction: '改写',
        model: 'm',
        previous_content: 'old',
      }],
    }
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) return Promise.resolve({ data: mkRecord() })
      if (url.includes('/assets/a1/publish-records')) return Promise.resolve({ data: [mkRecord()] })
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [chapterWithDiff] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText(/章节级 diff/)).toBeInTheDocument())
    expect(screen.getByText(/改写/)).toBeInTheDocument()
  })

  it('visibility badge rendered for public_link', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) {
        return Promise.resolve({
          data: mkRecord({ destination: 'public_link', visibility: 'team' }),
        })
      }
      if (url.includes('/assets/a1/publish-records')) {
        return Promise.resolve({ data: [mkRecord({ destination: 'public_link', visibility: 'team' })] })
      }
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('团队可见')).toBeInTheDocument())
  })

  it('pending status shows 准备中 button when no url', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) {
        return Promise.resolve({ data: mkRecord({ status: 'pending', url: null }) })
      }
      if (url.includes('/assets/a1/publish-records')) {
        return Promise.resolve({ data: [mkRecord({ status: 'pending', url: null })] })
      }
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('准备中')).toBeInTheDocument())
  })

  it('failed record shows error text', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/publish-records/rec1')) {
        return Promise.resolve({ data: mkRecord({ status: 'failed', error: '推送失败: 503' }) })
      }
      if (url.includes('/assets/a1/publish-records')) {
        return Promise.resolve({ data: [mkRecord({ status: 'failed', error: '推送失败: 503' })] })
      }
      if (url.includes('/assets/a1/chapters')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: mkAsset })
    })
    render(withWrappers(<PublishReceiptPage />))
    await waitFor(() => expect(screen.getByText('推送失败: 503')).toBeInTheDocument())
  })
})
