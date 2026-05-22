/**
 * EvidenceSourceCard + EvidenceDrawer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { EvidenceSourceCard } from './EvidenceSourceCard'
import { EvidenceDrawer } from './EvidenceDrawer'
import { api } from '@/lib/api'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import type { Evidence } from '@/types/api'


const mkEvidence = (overrides: Partial<Evidence> = {}): Evidence => ({
  id: 'ev1',
  chapter_id: 'c1',
  event_id: 'e1',
  event_version: 1,
  span_start: 0,
  span_end: 10,
  citation_text: '[1]',
  manually_added: false,
  stale: false,
  trust_score: 0.85,
  citation_strength: 0.7,
  event_preview: {
    event_id: 'e1',
    title: 'PR #42 · feat: foo',
    source_type: 'github',
    source_ref: 'org/repo#42',
    author_name: 'Alice',
    author_email: 'a@example.com',
    occurred_at: new Date().toISOString(),
    content_excerpt: '这是原文摘录的内容片段',
    external_url: 'https://github.com/org/repo/pull/42',
  },
  ...overrides,
})


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


// ─── EvidenceSourceCard ─────────────────────────────────


describe('EvidenceSourceCard', () => {
  it('renders title + source + excerpt + author', () => {
    render(<EvidenceSourceCard evidence={mkEvidence()} />)
    expect(screen.getByText('PR #42 · feat: foo')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByText('org/repo#42')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('a@example.com')).toBeInTheDocument()
    expect(screen.getByText('这是原文摘录的内容片段')).toBeInTheDocument()
  })

  it('trust + citation badges rendered (high tone)', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({ trust_score: 0.9, citation_strength: 0.92 })} />)
    expect(screen.getByText('trust')).toBeInTheDocument()
    expect(screen.getByText('citation')).toBeInTheDocument()
    // 90 + 92 both visible
    expect(screen.getByText('90')).toBeInTheDocument()
    expect(screen.getByText('92')).toBeInTheDocument()
  })

  it('manually_added badge rendered', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({ manually_added: true })} />)
    expect(screen.getByText('手动添加')).toBeInTheDocument()
  })

  it('stale badge rendered', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({ stale: true })} />)
    expect(screen.getByText('已过期')).toBeInTheDocument()
  })

  it('external_url null: shows 无外链 disabled button', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({
      event_preview: { ...mkEvidence().event_preview, external_url: null },
    })} />)
    expect(screen.getByText('无外链')).toBeInTheDocument()
    expect(screen.getByText('无外链').closest('button')).toBeDisabled()
  })

  it('external_url: 在源头打开 link rendered', () => {
    render(<EvidenceSourceCard evidence={mkEvidence()} />)
    const link = screen.getByText('在源头打开').closest('a')
    expect(link).toHaveAttribute('href', 'https://github.com/org/repo/pull/42')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('different source types render correct labels', () => {
    const types: Array<[string, string]> = [
      ['github', 'GitHub'],
      ['claude_code', 'Claude Code'],
      ['cursor', 'Cursor'],
      ['vscode', 'VS Code'],
      ['local_file', '本地文档'],
      ['manual', '手动录入'],
      ['unknown_x', 'unknown_x'],
    ]
    for (const [st, label] of types) {
      const { unmount } = render(<EvidenceSourceCard evidence={mkEvidence({
        event_preview: { ...mkEvidence().event_preview, source_type: st },
      })} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    }
  })

  it('title null → (无标题)', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({
      event_preview: { ...mkEvidence().event_preview, title: null },
    })} />)
    expect(screen.getByText('(无标题)')).toBeInTheDocument()
  })

  it('author null → 未知', () => {
    render(<EvidenceSourceCard evidence={mkEvidence({
      event_preview: { ...mkEvidence().event_preview, author_name: null, author_email: null },
    })} />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  it('low trust (<0.5) → warning tone', () => {
    const { container } = render(<EvidenceSourceCard evidence={mkEvidence({ trust_score: 0.3 })} />)
    expect(container.querySelector('.text-warning-dark')).not.toBeNull()
  })

  it('medium trust (0.5-0.8) → info tone', () => {
    const { container } = render(<EvidenceSourceCard evidence={mkEvidence({ trust_score: 0.65 })} />)
    expect(container.querySelector('.text-info-dark')).not.toBeNull()
  })
})


// ─── EvidenceDrawer ──────────────────────────────────────


describe('EvidenceDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useDocumentUiStore.setState({
      evidenceOpen: false,
      evidenceChapterId: null,
      activeEvidenceId: null,
    })
  })

  it('hidden when not open', () => {
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    expect(screen.queryByText('证据链')).toBeNull()
  })

  it('open + loading state', async () => {
    let resolveFn: ((v: { data: Evidence[] }) => void) | null = null
    vi.spyOn(api, 'get').mockReturnValueOnce(
      new Promise((res) => { resolveFn = res }),
    )
    useDocumentUiStore.setState({ evidenceOpen: true, evidenceChapterId: 'c1' })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    expect(screen.getByText(/加载证据中/)).toBeInTheDocument()
    resolveFn!({ data: [] })
  })

  it('renders list of evidence with tab buttons', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        mkEvidence({ id: 'ev1' }),
        mkEvidence({ id: 'ev2', event_preview: { ...mkEvidence().event_preview, title: '第二证据' } }),
      ],
    })
    useDocumentUiStore.setState({ evidenceOpen: true, evidenceChapterId: 'c1' })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    await waitFor(() => {
      expect(screen.getByText(/2 条/)).toBeInTheDocument()
      expect(screen.getByLabelText('查看证据 1')).toBeInTheDocument()
      expect(screen.getByLabelText('查看证据 2')).toBeInTheDocument()
    })
  })

  it('clicking tab button switches active evidence', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        mkEvidence({ id: 'ev1' }),
        mkEvidence({ id: 'ev2', event_preview: { ...mkEvidence().event_preview, title: '第二证据' } }),
      ],
    })
    useDocumentUiStore.setState({ evidenceOpen: true, evidenceChapterId: 'c1' })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    await waitFor(() => expect(screen.getByLabelText('查看证据 2')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('查看证据 2'))
    await waitFor(() => {
      expect(useDocumentUiStore.getState().activeEvidenceId).toBe('ev2')
      expect(screen.getByText('第二证据')).toBeInTheDocument()
    })
  })

  it('empty list shows DrawerEmpty', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    useDocumentUiStore.setState({ evidenceOpen: true, evidenceChapterId: 'c1' })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    await waitFor(() =>
      expect(screen.getByText('本章节暂无证据引用')).toBeInTheDocument(),
    )
  })

  it('error state with retry', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new Error('fail'))
    useDocumentUiStore.setState({ evidenceOpen: true, evidenceChapterId: 'c1' })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    await waitFor(() => expect(screen.getByText('证据加载失败')).toBeInTheDocument())
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  it('auto-selects first evidence when no activeId', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [mkEvidence({ id: 'ev-auto' })],
    })
    useDocumentUiStore.setState({
      evidenceOpen: true,
      evidenceChapterId: 'c1',
      activeEvidenceId: null,
    })
    render(withQuery(<EvidenceDrawer assetId="a1" />))
    await waitFor(() =>
      expect(useDocumentUiStore.getState().activeEvidenceId).toBe('ev-auto'),
    )
  })
})
