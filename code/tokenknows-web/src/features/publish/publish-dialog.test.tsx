/**
 * PublishDialog · T11 发布 dialog.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { PublishDialog } from './PublishDialog'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Asset } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1',
  project_id: 'p1',
  type: 'weekly_report',
  title: '周报',
  status: 'approved',
  current_version: 2,
  template_id: null,
  created_by: 'u1',
  approval_state: 'approved',
  redaction_state: 'all_confirmed',
  metrics: { coverage: 0.9, citation_density: 0.5, slop_score: 0.1, similarity: 0.3 },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:assetId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('PublishDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({ publishOpen: false })
  })

  it('hidden when closed', () => {
    render(withWrappers(<PublishDialog assetId="a1" />))
    expect(screen.queryByText('发布文档')).toBeNull()
  })

  it('renders title + 3 destination radios when open', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('发布文档')).toBeInTheDocument())
    expect(screen.getByText('站内文档库')).toBeInTheDocument()
    expect(screen.getByText('公开链接')).toBeInTheDocument()
    expect(screen.getByText('导出 Markdown')).toBeInTheDocument()
  })

  it('shows block reason when status=generating', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset({ status: 'generating' }) })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('文档仍在生成中')).toBeInTheDocument())
  })

  it('shows block reason when status=in_review', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset({ status: 'in_review' }) })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('文档正在审批')).toBeInTheDocument())
  })

  it('shows block reason when status=archived', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset({ status: 'archived' }) })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('文档已归档')).toBeInTheDocument())
  })

  it('shows block reason when status=published (再次发布提示)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset({ status: 'published' }) })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('文档已发布')).toBeInTheDocument())
  })

  it('shows high similarity warning (>85%)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: mkAsset({ metrics: { coverage: 0.9, citation_density: 0.5, slop_score: 0.1, similarity: 0.95 } }),
    })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText(/相似度 95%/)).toBeInTheDocument())
  })

  it('submit button disabled when confirm not checked', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('确认发布')).toBeInTheDocument())
    expect(screen.getByText('确认发布').closest('button')).toBeDisabled()
  })

  it('clicking public_link shows visibility fieldset', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('公开链接')).toBeInTheDocument())
    const publicLinkRadio = screen.getAllByRole('radio').find((r) =>
      (r as HTMLInputElement).value === 'public_link',
    ) as HTMLInputElement
    fireEvent.click(publicLinkRadio)
    await waitFor(() => expect(screen.getByText(/可见范围/)).toBeInTheDocument())
    expect(screen.getByText(/团队内/)).toBeInTheDocument()
    expect(screen.getByText(/公开 \(任何人/)).toBeInTheDocument()
  })

  it('visibility public radio toggles', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('公开链接')).toBeInTheDocument())
    const publicLinkRadio = screen.getAllByRole('radio').find((r) =>
      (r as HTMLInputElement).value === 'public_link',
    ) as HTMLInputElement
    fireEvent.click(publicLinkRadio)
    await waitFor(() => expect(screen.getByText(/可见范围/)).toBeInTheDocument())
    const publicRadio = screen.getAllByRole('radio').find((r) =>
      (r as HTMLInputElement).value === 'public',
    ) as HTMLInputElement
    fireEvent.click(publicRadio)
    expect(publicRadio.checked).toBe(true)
  })

  it('successful publish POST + navigate', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: [{ id: 'rec1', destination: 'internal', url: '/r/rec1', published_at: new Date().toISOString() }],
    })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('确认发布')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('确认发布'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
  })

  it('error displayed on failure', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    vi.spyOn(api, 'post').mockRejectedValue(new Error('发布失败'))
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('确认发布')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('确认发布'))
    await waitFor(() => expect(screen.getByText(/发布失败/)).toBeInTheDocument())
  })

  it('cancel closes dialog', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('取消')).toBeInTheDocument())
    fireEvent.click(screen.getByText('取消'))
    await waitFor(() => expect(useDocumentUiStore.getState().publishOpen).toBe(false))
  })

  it('asset.status=draft does not block (mvp draft can publish)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset({ status: 'draft', approval_state: 'pending' }) })
    useDocumentUiStore.setState({ publishOpen: true })
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('发布文档')).toBeInTheDocument())
    // no block reason banner
    expect(screen.queryByText('文档仍在生成中')).toBeNull()
  })
})
