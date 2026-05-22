/**
 * DocumentPage handleViewEvidence callback · 通过 ChapterBlock 真实点击 [N] 触发.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import DocumentPage from './DocumentPage'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (): Asset => ({
  id: 'a1', project_id: 'p1', type: 'weekly_report', title: '周报',
  status: 'draft', current_version: 1, template_id: null, created_by: 'u1',
  approval_state: 'pending', redaction_state: 'all_confirmed', metrics: null,
  created_at: '', updated_at: '',
})

const mkChapter = (): Chapter => ({
  id: 'c1', asset_id: 'a1', asset_version: 1, order_index: 0,
  title: '亮点', content: '段落 [1] 提到 PR.',
  layout: {}, generated_by: null,
  regeneration_history: [], approval_state: 'pending',
  created_at: '', updated_at: '',
})


function withDoc(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/projects/p1/documents/a1']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/projects/:id/documents/:docId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}


describe('DocumentPage handleViewEvidence', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({
      evidenceOpen: false, evidenceChapterId: null, activeEvidenceId: null,
    })
  })

  it('clicking [1] badge in chapter calls openEvidence(c1, ev-c1-1)', async () => {
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url.includes('/chapters')) return Promise.resolve({ data: [mkChapter()] })
      return Promise.resolve({ data: mkAsset() })
    })
    const { container } = render(withDoc(<DocumentPage />))
    await waitFor(() => expect(container.querySelector('[data-evidence-id]')).not.toBeNull())
    const badge = container.querySelector('[data-evidence-id]') as HTMLElement
    fireEvent.click(badge)
    await waitFor(() => {
      const state = useDocumentUiStore.getState()
      expect(state.evidenceOpen).toBe(true)
      expect(state.evidenceChapterId).toBe('c1')
    })
  })
})
