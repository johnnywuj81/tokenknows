/**
 * RegenerateDialog + PublishDialog pending spinner branches.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { RegenerateDialog } from './page/components/RegenerateDialog'
import { PublishDialog } from '../publish/PublishDialog'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Asset, Chapter } from '@/types/api'


function withWrappers(ui: ReactNode, path = '/projects/p1/documents/a1') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:assetId" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


const mkChapter = (): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: 'T', content: '', layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
})

const mkAsset = (): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'approved', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'approved', redaction_state: 'all_confirmed', metrics: null,
  created_at: '', updated_at: '',
})


describe('RegenerateDialog pending', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({
      regenerateOpen: true, regenerateChapterId: 'c1',
    })
  })

  it('shows 重生成中… while POST pending', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [mkChapter()] })
    let resolvePost: ((v: unknown) => void) | null = null
    vi.spyOn(api, 'post').mockReturnValueOnce(
      new Promise((res) => { resolvePost = res }),
    )
    render(withWrappers(<RegenerateDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('重生成章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/重生成指令/), {
      target: { value: '更简洁地重写' },
    })
    fireEvent.click(screen.getByText('提交重生成'))
    await waitFor(() => expect(screen.getByText(/重生成中/)).toBeInTheDocument())
    resolvePost?.({ data: {} })
  })
})


describe('PublishDialog pending', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({ publishOpen: true })
  })

  it('shows 发布中… while POST pending', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: mkAsset() })
    let resolvePost: ((v: unknown) => void) | null = null
    vi.spyOn(api, 'post').mockReturnValueOnce(
      new Promise((res) => { resolvePost = res }),
    )
    render(withWrappers(<PublishDialog assetId="a1" />))
    await waitFor(() => expect(screen.getByText('发布文档')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('确认发布'))
    await waitFor(() => expect(screen.getByText(/发布中/)).toBeInTheDocument())
    resolvePost?.({
      data: [{ id: 'rec1', destination: 'internal', url: '/r/x', published_at: '' }],
    })
  })
})
