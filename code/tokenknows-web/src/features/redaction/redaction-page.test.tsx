/**
 * RedactionPage · T10 redaction confirmation panel.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import RedactionPage from './RedactionPage'
import { api } from '@/lib/api'
import type { Asset, RedactionItem, RedactionScanJob } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1',
  project_id: 'p1',
  type: 'weekly_report',
  title: '周报',
  status: 'draft',
  current_version: 1,
  template_id: null,
  created_by: 'u1',
  approval_state: 'pending',
  redaction_state: 'any_unresolved',
  metrics: null,
  created_at: '',
  updated_at: '',
  ...overrides,
})

const mkItem = (overrides: Partial<RedactionItem> = {}): RedactionItem => ({
  id: 'r1',
  chapter_id: 'c1',
  span_start: 0,
  span_end: 5,
  type: 'EMAIL',
  matched_text: 'foo@example.com',
  rule_source: 'rule',
  suggested_replacement: '[EMAIL]',
  status: 'pending',
  context_before: '...联系',
  context_after: '获取',
  ...overrides,
})

const mkJob = (items: RedactionItem[] = []): RedactionScanJob => ({
  id: 'job1',
  asset_id: 'a1',
  asset_version: 1,
  scan_at: new Date().toISOString(),
  status: 'completed',
  items,
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1/redaction']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId/redaction" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('RedactionPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows loading skeleton initially', () => {
    vi.spyOn(api, 'get').mockReturnValue(new Promise(() => {}))
    const { container } = render(withWrappers(<RedactionPage />))
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('error state on asset load failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('脱敏扫描失败')).toBeInTheDocument())
  })

  it('renders empty state when no items', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob([]) })
      if (url.endsWith('/assets/a1')) return Promise.resolve({ data: mkAsset({ redaction_state: 'all_confirmed' }) })
      return Promise.resolve({ data: null })
    })
    vi.spyOn(api, 'post').mockResolvedValue({ data: mkJob([]) })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('未命中敏感内容')).toBeInTheDocument())
  })

  it('renders items grouped by type', async () => {
    const items = [
      mkItem({ id: 'r1', type: 'EMAIL', matched_text: 'a@b.com' }),
      mkItem({ id: 'r2', type: 'API_KEY', matched_text: 'sk-abc' }),
    ]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      if (url.endsWith('/assets/a1')) return Promise.resolve({ data: mkAsset() })
      return Promise.resolve({ data: null })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('邮箱地址')).toBeInTheDocument())
    expect(screen.getByText('API 密钥')).toBeInTheDocument()
    // matched_text 在 code tag + mark 各出现一次
    expect(screen.getAllByText('a@b.com').length).toBeGreaterThan(0)
    expect(screen.getAllByText('sk-abc').length).toBeGreaterThan(0)
  })

  it('clicking 脱敏 invokes confirm POST', async () => {
    const items = [mkItem()]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mkJob([]) })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('脱敏')).toBeInTheDocument())
    fireEvent.click(screen.getByText('脱敏'))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        '/assets/a1/redaction/confirm',
        { item_ids: ['r1'] },
      ),
    )
  })

  it('豁免 button opens dialog with reason input', async () => {
    const items = [mkItem({ matched_text: 'sensitive@x.com' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('豁免')).toBeInTheDocument())
    fireEvent.click(screen.getByText('豁免'))
    await waitFor(() => expect(screen.getByText('豁免脱敏')).toBeInTheDocument())
    // sensitive@x.com 出现两次 (item card + dialog body)
    const matches = screen.getAllByText('sensitive@x.com')
    expect(matches.length).toBeGreaterThan(0)
  })

  it('豁免 submit fires exempt POST', async () => {
    const items = [mkItem({ id: 'r-x', type: 'CUSTOMER', matched_text: 'AcmeCorp' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mkJob(items) })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('豁免')).toBeInTheDocument())
    fireEvent.click(screen.getByText('豁免'))
    await waitFor(() => expect(screen.getByText('豁免脱敏')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/豁免理由/), {
      target: { value: '公开案例无敏感性' },
    })
    fireEvent.click(screen.getByText('确认豁免'))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        '/assets/a1/redaction/exempt',
        { item_id: 'r-x', reason: '公开案例无敏感性' },
      ),
    )
  })

  it('豁免 confirm button disabled when reason < 3 chars', async () => {
    const items = [mkItem()]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('豁免')).toBeInTheDocument())
    fireEvent.click(screen.getByText('豁免'))
    await waitFor(() => expect(screen.getByText('豁免脱敏')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/豁免理由/), { target: { value: 'ab' } })
    expect(screen.getByText('确认豁免').closest('button')).toBeDisabled()
  })

  it('exemption dialog cancel resets state', async () => {
    const items = [mkItem()]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('豁免')).toBeInTheDocument())
    fireEvent.click(screen.getByText('豁免'))
    await waitFor(() => expect(screen.getByText('豁免脱敏')).toBeInTheDocument())
    fireEvent.click(screen.getByText('取消'))
    await waitFor(() => expect(screen.queryByText('豁免脱敏')).toBeNull())
  })

  it('confirmed item shows 已脱敏 + no action buttons', async () => {
    const items = [mkItem({ status: 'confirmed' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('已脱敏')).toBeInTheDocument())
    expect(screen.queryByText('脱敏')).toBeNull()
    expect(screen.queryByText('豁免')).toBeNull()
  })

  it('exempted item shows 已豁免 + reason text', async () => {
    const items = [mkItem({ status: 'exempted', reason: '公开案例', matched_text: 'X' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('已豁免')).toBeInTheDocument())
    expect(screen.getByText(/公开案例/)).toBeInTheDocument()
  })

  it('all confirmed: 进入发布 button enabled', async () => {
    const items = [mkItem({ status: 'confirmed' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset({ redaction_state: 'all_confirmed' }) })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('进入发布 (T11)')).toBeInTheDocument())
    expect(screen.getByText('进入发布 (T11)').closest('button')).not.toBeDisabled()
  })

  it('pending items: 进入发布 disabled', async () => {
    const items = [mkItem({ status: 'pending' })]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('进入发布 (T11)')).toBeInTheDocument())
    expect(screen.getByText('进入发布 (T11)').closest('button')).toBeDisabled()
  })

  it('重新扫描 button fires trigger', async () => {
    const items = [mkItem()]
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob(items) })
      return Promise.resolve({ data: mkAsset() })
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mkJob(items) })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText('重新扫描')).toBeInTheDocument())
    fireEvent.click(screen.getByText('重新扫描'))
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/assets/a1/redaction/scan'),
    )
  })

  it('back button navigates', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/redaction/scan')) return Promise.resolve({ data: mkJob([]) })
      return Promise.resolve({ data: mkAsset({ redaction_state: 'all_confirmed' }) })
    })
    render(withWrappers(<RedactionPage />))
    await waitFor(() => expect(screen.getByText(/返回文档/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/返回文档/))
    // no error
  })
})
