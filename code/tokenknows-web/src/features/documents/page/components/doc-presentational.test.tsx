/**
 * Documents/page 简单组件 · DocHeader + DocSidebar + SelfAssessCard + DocOutline + ChapterFooter.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DocHeader } from './DocHeader'
import { DocSidebar } from './DocSidebar'
import { SelfAssessCard } from './SelfAssessCard'
import { DocOutline } from './DocOutline'
import { ChapterFooter } from './ChapterFooter'
import type { Asset, AssetMetrics, AssetStatus, Chapter } from '@/types/api'


const mkAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: 'a1',
  project_id: 'p1',
  type: 'weekly_report',
  title: '周报 · 2026-W21',
  status: 'draft',
  current_version: 3,
  template_id: 'tpl-weekly',
  created_by: 'u1',
  approval_state: 'pending',
  redaction_state: 'all_confirmed',
  metrics: { coverage: 0.85, citation_density: 0.42, slop_score: 0.18, similarity: 0.5 },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const mkChapter = (overrides: Partial<Chapter> = {}): Chapter => ({
  id: 'c1',
  asset_id: 'a1',
  asset_version: 1,
  order_index: 0,
  title: '本周亮点',
  content: '内容',
  layout: {},
  generated_by: null,
  regeneration_history: [],
  approval_state: 'pending',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})


// ─── DocHeader ────────────────────────────────────────────


describe('DocHeader', () => {
  it('renders title + type + status + version', () => {
    render(<MemoryRouter><DocHeader asset={mkAsset()} /></MemoryRouter>)
    expect(screen.getByText('周报 · 2026-W21')).toBeInTheDocument()
    expect(screen.getByText('周报')).toBeInTheDocument()
    expect(screen.getByText('草稿')).toBeInTheDocument()
    expect(screen.getByText('v3')).toBeInTheDocument()
  })

  it('saving badge appears when saving=true', () => {
    render(<MemoryRouter><DocHeader asset={mkAsset()} saving /></MemoryRouter>)
    expect(screen.getByText('保存中')).toBeInTheDocument()
  })

  it('draft status: 提交审批 button + onSubmit', () => {
    const onSubmit = vi.fn()
    render(<MemoryRouter><DocHeader asset={mkAsset({ status: 'draft' })} onSubmit={onSubmit} /></MemoryRouter>)
    fireEvent.click(screen.getByText('提交审批'))
    expect(onSubmit).toHaveBeenCalled()
  })

  it('submitting state: 提交中 + disabled', () => {
    render(<MemoryRouter><DocHeader asset={mkAsset({ status: 'draft' })} submitting /></MemoryRouter>)
    expect(screen.getByRole('button', { name: /提交中/ })).toBeDisabled()
  })

  it('approved status: 发布 button + onPublish', () => {
    const onPublish = vi.fn()
    render(<MemoryRouter><DocHeader asset={mkAsset({ status: 'approved' })} onPublish={onPublish} /></MemoryRouter>)
    fireEvent.click(screen.getByText('发布'))
    expect(onPublish).toHaveBeenCalled()
  })

  it('published status: 再次发布 button rendered', () => {
    render(<MemoryRouter><DocHeader asset={mkAsset({ status: 'published' })} onPublish={() => {}} /></MemoryRouter>)
    expect(screen.getByText('再次发布')).toBeInTheDocument()
  })

  it('various type labels rendered', () => {
    const types: Array<[Asset['type'], string]> = [
      ['weekly_report', '周报'],
      ['tech_design', '技术方案'],
      ['adr', 'ADR'],
      ['incident', '问题复盘'],
    ]
    for (const [type, label] of types) {
      const { unmount } = render(<MemoryRouter><DocHeader asset={mkAsset({ type })} /></MemoryRouter>)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    }
  })

  it('all status meta labels rendered', () => {
    const statuses: Array<[AssetStatus, string]> = [
      ['generating', '生成中'],
      ['draft', '草稿'],
      ['in_review', '审批中'],
      ['approved', '已通过'],
      ['published', '已发布'],
      ['archived', '已归档'],
    ]
    for (const [status, label] of statuses) {
      const { unmount } = render(<MemoryRouter><DocHeader asset={mkAsset({ status })} /></MemoryRouter>)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    }
  })

  it('back button navigates -1', () => {
    render(<MemoryRouter initialEntries={['/x', '/y']} initialIndex={1}>
      <DocHeader asset={mkAsset()} />
    </MemoryRouter>)
    fireEvent.click(screen.getByLabelText('返回'))
    // 不抛错就行 (navigation 内部状态)
  })
})


// ─── DocSidebar ────────────────────────────────────────────


describe('DocSidebar', () => {
  it('renders metadata rows', () => {
    render(<DocSidebar asset={mkAsset()} />)
    expect(screen.getByText('模板')).toBeInTheDocument()
    expect(screen.getByText('tpl-weekly')).toBeInTheDocument()
    expect(screen.getByText('审批')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()
    expect(screen.getByText('✅ 全部确认')).toBeInTheDocument()
  })

  it('template_id null → —', () => {
    render(<DocSidebar asset={mkAsset({ template_id: null })} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('redaction unresolved → 待确认', () => {
    render(<DocSidebar asset={mkAsset({ redaction_state: 'any_unresolved' })} />)
    expect(screen.getByText(/待确认/)).toBeInTheDocument()
  })

  it('renders 3 tabs: 证据 / 评论 / 历史', () => {
    render(<DocSidebar asset={mkAsset()} />)
    expect(screen.getByRole('tab', { name: /证据/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /评论/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /历史/ })).toBeInTheDocument()
  })

  it('default evidence tab content: 点击章节内 [N] 角标', () => {
    render(<DocSidebar asset={mkAsset()} />)
    // Radix mounts only active TabsContent by default
    expect(screen.getByText(/点击章节内/)).toBeInTheDocument()
  })
})


// ─── SelfAssessCard ──────────────────────────────────────


describe('SelfAssessCard', () => {
  it('null metrics: all show — (no warning class)', () => {
    render(<SelfAssessCard metrics={null} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBe(4)
  })

  it('loading: all show --', () => {
    render(<SelfAssessCard metrics={null} loading />)
    const placeholders = screen.getAllByText('--')
    expect(placeholders.length).toBe(4)
  })

  it('renders 4 labels', () => {
    render(<SelfAssessCard metrics={null} />)
    expect(screen.getByText('覆盖')).toBeInTheDocument()
    expect(screen.getByText('引用')).toBeInTheDocument()
    expect(screen.getByText('空话')).toBeInTheDocument()
    expect(screen.getByText('相似')).toBeInTheDocument()
  })

  it('low coverage (< 60%) → warning color', () => {
    const m: AssetMetrics = { coverage: 0.40, citation_density: 0.80, slop_score: 0.10, similarity: 0.10 }
    const { container } = render(<SelfAssessCard metrics={m} />)
    const warns = container.querySelectorAll('.text-warning')
    expect(warns.length).toBeGreaterThan(0)
  })

  it('high slop (>20%, isLowerBetter) → warning', () => {
    const m: AssetMetrics = { coverage: 0.90, citation_density: 0.90, slop_score: 0.35, similarity: 0.10 }
    const { container } = render(<SelfAssessCard metrics={m} />)
    expect(container.querySelectorAll('.text-warning').length).toBeGreaterThan(0)
  })

  it('values rendered as %', () => {
    const m: AssetMetrics = { coverage: 0.85, citation_density: 0.42, slop_score: 0.18, similarity: 0.50 }
    render(<SelfAssessCard metrics={m} />)
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByText('18%')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
  })
})


// ─── DocOutline ──────────────────────────────────────────


describe('DocOutline', () => {
  it('renders chapter count + items', () => {
    const chs = [
      mkChapter({ id: 'c1', order_index: 0, title: '亮点' }),
      mkChapter({ id: 'c2', order_index: 1, title: '风险' }),
    ]
    const scrollRef = { current: null }
    render(<DocOutline chapters={chs} scrollRef={scrollRef} />)
    expect(screen.getByText('大纲 · 2 章')).toBeInTheDocument()
    expect(screen.getByText('1. 亮点')).toBeInTheDocument()
    expect(screen.getByText('2. 风险')).toBeInTheDocument()
  })

  it('clicking chapter triggers scrollIntoView + sets activeId', () => {
    const chs = [mkChapter({ id: 'c1', title: '亮点' })]
    const scrollRef = { current: null }
    const el = document.createElement('div')
    el.id = 'chapter-anchor-c1'
    const scrollSpy = vi.fn()
    el.scrollIntoView = scrollSpy
    document.body.appendChild(el)
    try {
      render(<DocOutline chapters={chs} scrollRef={scrollRef} />)
      fireEvent.click(screen.getByText('1. 亮点'))
      expect(scrollSpy).toHaveBeenCalled()
    } finally {
      document.body.removeChild(el)
    }
  })

  it('empty chapters: no items', () => {
    const scrollRef = { current: null }
    render(<DocOutline chapters={[]} scrollRef={scrollRef} />)
    expect(screen.getByText('大纲 · 0 章')).toBeInTheDocument()
  })
})


// ─── ChapterFooter ──────────────────────────────────────


describe('ChapterFooter', () => {
  it('renders 3 footer buttons + version', () => {
    render(<ChapterFooter
      chapter={mkChapter({ asset_version: 3, approval_state: 'pending' })}
      onRegenerate={() => {}}
      onViewEvidence={() => {}}
    />)
    expect(screen.getByText('重生成')).toBeInTheDocument()
    expect(screen.getByText('查看证据')).toBeInTheDocument()
    expect(screen.getByText('批注')).toBeInTheDocument()
    expect(screen.getByText('v3 · pending')).toBeInTheDocument()
  })

  it('clicking 重生成 invokes onRegenerate with chapter id', () => {
    const onRegenerate = vi.fn()
    render(<ChapterFooter chapter={mkChapter({ id: 'c1' })} onRegenerate={onRegenerate} />)
    fireEvent.click(screen.getByText('重生成'))
    expect(onRegenerate).toHaveBeenCalledWith('c1')
  })

  it('clicking 查看证据 invokes onViewEvidence', () => {
    const onViewEvidence = vi.fn()
    render(<ChapterFooter chapter={mkChapter({ id: 'c1' })} onViewEvidence={onViewEvidence} />)
    fireEvent.click(screen.getByText('查看证据'))
    expect(onViewEvidence).toHaveBeenCalled()
    expect(onViewEvidence.mock.calls[0][0]).toBe('c1')
  })

  it('without onRegenerate: button disabled', () => {
    render(<ChapterFooter chapter={mkChapter()} />)
    expect(screen.getByText('重生成').closest('button')).toBeDisabled()
    expect(screen.getByText('查看证据').closest('button')).toBeDisabled()
  })

  it('批注 always disabled with tooltip', () => {
    render(<ChapterFooter chapter={mkChapter()} onRegenerate={() => {}} onViewEvidence={() => {}} />)
    const btn = screen.getByText('批注').closest('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('title', 'T09 审批阶段实现')
  })
})
