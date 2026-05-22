/**
 * DocumentListPage · handleClone + confirmDelete + delete dialog flow.
 *
 * 通过 mock DocumentCard 暴露简单 buttons, 绕开 Radix DropdownMenu portal 测试难点.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '@/lib/api'
import type { Asset } from '@/types/api'


// Mock DocumentCard 提供直接的 clone / delete buttons
vi.mock('./list/DocumentCard', () => ({
  DocumentCard: ({
    asset,
    onClone,
    onDelete,
  }: {
    asset: Asset
    projectId: string
    onClone: (id: string) => void
    onDelete: (id: string, title: string) => void
  }) => (
    <div data-testid={`card-${asset.id}`}>
      <span>{asset.title}</span>
      <button type="button" data-testid={`clone-${asset.id}`} onClick={() => onClone(asset.id)}>
        clone
      </button>
      <button
        type="button"
        data-testid={`delete-${asset.id}`}
        onClick={() => onDelete(asset.id, asset.title)}
      >
        delete
      </button>
    </div>
  ),
}))


const { default: DocumentListPage } = await import('./DocumentListPage')


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'draft', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  ...overrides,
})


function withList(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('DocumentListPage delete + clone flows', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('clone button: POST /projects/:id/assets/:assetId/clone', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset({ id: 'a-x', title: '周报 X' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({
      data: mkAsset({ id: 'a-cloned' }),
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('周报 X')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('clone-a-x'))
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled()
      expect(postSpy.mock.calls[0][0]).toContain('a-x')
    })
  })

  it('delete button: opens dialog with title', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset({ id: 'a-x', title: '待删文档' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getAllByText('待删文档').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByTestId('delete-a-x'))
    await waitFor(() => expect(screen.getByText('删除文档')).toBeInTheDocument())
    expect(screen.getAllByText('待删文档').length).toBeGreaterThan(0)
  })

  it('confirm delete: DELETE /assets/:id + closes dialog', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset({ id: 'a-del', title: '要删的' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    const deleteSpy = vi.spyOn(api, 'delete').mockResolvedValue({ data: {} })
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByText('要删的')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('delete-a-del'))
    await waitFor(() => expect(screen.getByText('确认删除')).toBeInTheDocument())
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => expect(deleteSpy).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('删除文档')).toBeNull())
  })

  it('cancel delete: closes dialog without DELETE', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        data: [mkAsset({ id: 'a-x' })],
        meta: { total: 1, cursor: null, has_more: false },
      },
    })
    const deleteSpy = vi.spyOn(api, 'delete')
    render(withList(<DocumentListPage />))
    await waitFor(() => expect(screen.getByTestId('delete-a-x')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('delete-a-x'))
    await waitFor(() => expect(screen.getByText('删除文档')).toBeInTheDocument())
    fireEvent.click(screen.getByText('取消'))
    await waitFor(() => expect(screen.queryByText('删除文档')).toBeNull())
    expect(deleteSpy).not.toHaveBeenCalled()
  })
})
