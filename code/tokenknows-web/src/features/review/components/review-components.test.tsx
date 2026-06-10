/**
 * Review components · BottomActionBar + ApprovalSidebar.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { BottomActionBar } from './BottomActionBar'
import { ApprovalSidebar } from './ApprovalSidebar'
import { api } from '@/lib/api'
import type { Asset, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1',
  project_id: 'p1',
  type: 'weekly_report',
  title: '周报',
  status: 'in_review',
  current_version: 1,
  template_id: null,
  created_by: 'u1',
  approval_state: 'pending',
  redaction_state: 'all_confirmed',
  metrics: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '亮点',
  content: '',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  redacted_spans: [],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
}


// ─── BottomActionBar ─────────────────────────────────────


describe('BottomActionBar', () => {
  it('shows progress: 0 通过 0 退回 with all pending', () => {
    const chs = [mkChapter({ id: 'c1' }), mkChapter({ id: 'c2' })]
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={chs} projectId="p1" onAllApproved={() => {}} />
    </MemoryRouter>)
    expect(screen.getByText('审批进度: 0 通过 · 0 退回 · 2 待审')).toBeInTheDocument()
  })

  it('all approved: 全部通过 button enabled + invokes callback', () => {
    const onAll = vi.fn()
    const chs = [
      mkChapter({ id: 'c1', approval_state: 'approved' }),
      mkChapter({ id: 'c2', approval_state: 'approved' }),
    ]
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={chs} projectId="p1" onAllApproved={onAll} />
    </MemoryRouter>)
    const btn = screen.getByText(/全部通过/).closest('button')
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn!)
    expect(onAll).toHaveBeenCalled()
  })

  it('has rejected: 退回修改 enabled + navigates', () => {
    const chs = [
      mkChapter({ id: 'c1', approval_state: 'rejected' }),
      mkChapter({ id: 'c2', approval_state: 'pending' }),
    ]
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={chs} projectId="p1" onAllApproved={() => {}} />
    </MemoryRouter>)
    const btn = screen.getByText('退回修改').closest('button')
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn!)
    // navigation should not throw
  })

  it('no rejected: 退回修改 disabled', () => {
    const chs = [mkChapter({ approval_state: 'pending' })]
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={chs} projectId="p1" onAllApproved={() => {}} />
    </MemoryRouter>)
    expect(screen.getByText('退回修改').closest('button')).toBeDisabled()
  })

  it('empty chapters: 全部通过 disabled', () => {
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={[]} projectId="p1" onAllApproved={() => {}} />
    </MemoryRouter>)
    expect(screen.getByText(/全部通过/).closest('button')).toBeDisabled()
  })

  it('保存进度 button rendered + clickable', () => {
    render(<MemoryRouter>
      <BottomActionBar asset={mkAsset()} chapters={[]} projectId="p1" onAllApproved={() => {}} />
    </MemoryRouter>)
    fireEvent.click(screen.getByText('保存进度'))
    // no error
  })
})


// ─── ApprovalSidebar ─────────────────────────────────────


describe('ApprovalSidebar', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders all chapters with state badges', () => {
    const chs = [
      mkChapter({ id: 'c1', title: '亮点', approval_state: 'pending' }),
      mkChapter({ id: 'c2', title: '风险', approval_state: 'approved' }),
      mkChapter({ id: 'c3', title: '展望', approval_state: 'rejected' }),
    ]
    render(withWrappers(<ApprovalSidebar
      assetId="a1"
      chapters={chs}
      onScrollToChapter={() => {}}
    />))
    expect(screen.getByText('亮点')).toBeInTheDocument()
    expect(screen.getByText('待审批')).toBeInTheDocument()
    expect(screen.getByText('已通过')).toBeInTheDocument()
    expect(screen.getByText('已退回')).toBeInTheDocument()
  })

  it('clicking title scrolls to chapter', () => {
    const onScroll = vi.fn()
    const chs = [mkChapter({ id: 'c1', title: '亮点' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={onScroll} />))
    fireEvent.click(screen.getByText('亮点'))
    expect(onScroll).toHaveBeenCalledWith('c1')
  })

  it('clicking 通过 fires approve mutation', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    const chs = [mkChapter({ id: 'c1', approval_state: 'pending' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    fireEvent.click(screen.getByText('通过'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
  })

  it('通过 disabled when already approved', () => {
    const chs = [mkChapter({ id: 'c1', approval_state: 'approved' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    expect(screen.getByText('通过').closest('button')).toBeDisabled()
  })

  it('clicking 退回 opens reject dialog', async () => {
    const chs = [mkChapter({ id: 'c1', title: '亮点' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    fireEvent.click(screen.getByText('退回'))
    await waitFor(() => expect(screen.getByText('退回章节')).toBeInTheDocument())
    expect(screen.getByText(/§1 亮点/)).toBeInTheDocument()
  })

  it('reject submit disabled when reason < 3 chars', async () => {
    const chs = [mkChapter({ id: 'c1' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    fireEvent.click(screen.getByText('退回'))
    await waitFor(() => expect(screen.getByText('退回章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/退回原因/), { target: { value: 'ab' } })
    expect(screen.getByText('确认退回').closest('button')).toBeDisabled()
  })

  it('reject submit fires reject mutation + closes dialog', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    const chs = [mkChapter({ id: 'c1' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    fireEvent.click(screen.getByText('退回'))
    await waitFor(() => expect(screen.getByText('退回章节')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/退回原因/), {
      target: { value: '需要补充细节' },
    })
    fireEvent.click(screen.getByText('确认退回'))
    await waitFor(() => expect(postSpy).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('退回章节')).toBeNull())
  })

  it('cancel button closes reject dialog', async () => {
    const chs = [mkChapter({ id: 'c1' })]
    render(withWrappers(<ApprovalSidebar assetId="a1" chapters={chs} onScrollToChapter={() => {}} />))
    fireEvent.click(screen.getByText('退回'))
    await waitFor(() => expect(screen.getByText('退回章节')).toBeInTheDocument())
    fireEvent.click(screen.getByText('取消'))
    await waitFor(() => expect(screen.queryByText('退回章节')).toBeNull())
  })

  it('highlightChapterId applies ring', () => {
    const chs = [mkChapter({ id: 'c1' })]
    const { container } = render(withWrappers(<ApprovalSidebar
      assetId="a1"
      chapters={chs}
      highlightChapterId="c1"
      onScrollToChapter={() => {}}
    />))
    expect(container.querySelector('.ring-2.ring-accent-primary')).not.toBeNull()
  })
})
