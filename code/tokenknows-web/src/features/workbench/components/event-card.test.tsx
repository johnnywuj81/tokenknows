/**
 * EventCard · 全 event_type + source_type 分支覆盖.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EventCard } from './EventCard'
import type { Event, EventSourceType, EventType } from '@/types/api'


const mk = (overrides: Partial<Event> = {}): Event => ({
  id: 'e1', project_id: 'p1', source_type: 'github', source_ref: 'org/repo#1',
  external_id: 'ext1', version: 1, event_type: 'pr_event',
  occurred_at: new Date('2026-01-15T10:30:00').toISOString(),
  ingested_at: new Date().toISOString(),
  author: { name: 'Alice', email: null }, title: 'PR #1',
  content: 'c', payload: {}, redaction_state: 'raw',
  trust_score: 0.9, tags: [], content_hash: 'h',
  ...overrides,
})


describe('EventCard', () => {
  it('renders title + author + time + trust', () => {
    render(<EventCard event={mk({ title: 'feat: 加新功能' })} />)
    expect(screen.getByText('feat: 加新功能')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('org/repo#1')).toBeInTheDocument()
    expect(screen.getByText('90')).toBeInTheDocument()
  })

  it('clicks invokes onClick', () => {
    const onClick = vi.fn()
    render(<EventCard event={mk()} onClick={onClick} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalled()
  })

  it('title null → falls back to event_type label', () => {
    render(<EventCard event={mk({ title: null, event_type: 'commit' })} />)
    expect(screen.getByText('Commit')).toBeInTheDocument()
  })

  it('all event_type labels rendered correctly', () => {
    const types: Array<[EventType, string]> = [
      ['ai_conversation_turn', 'AI 对话'],
      ['tool_call', '工具调用'],
      ['code_change', '代码修改'],
      ['pr_event', 'PR 事件'],
      ['issue_event', 'Issue 事件'],
      ['commit', 'Commit'],
      ['local_document', '本地文档'],
      ['manual_note', '手动笔记'],
    ]
    for (const [t, label] of types) {
      const { unmount } = render(<EventCard event={mk({ title: null, event_type: t })} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    }
  })

  it('renders correct icon per source_type', () => {
    const sources: EventSourceType[] = ['github', 'claude_code', 'cursor', 'vscode', 'local_file', 'manual']
    for (const s of sources) {
      const { container, unmount } = render(<EventCard event={mk({ source_type: s, event_type: 'manual_note' })} />)
      // 验证有 svg 渲染 (icon)
      expect(container.querySelectorAll('svg').length).toBeGreaterThan(0)
      unmount()
    }
  })

  it('no author: no Avatar rendered', () => {
    render(<EventCard event={mk({ author: null })} />)
    expect(screen.queryByText('Alice')).toBeNull()
  })

  it('no trust_score: no badge rendered', () => {
    const { container } = render(<EventCard event={mk({ trust_score: null })} />)
    // 90 数字应该不出现
    expect(container.textContent).not.toContain('TRUST 90')
  })

  it('commit event: green side bar', () => {
    const { container } = render(<EventCard event={mk({ event_type: 'commit' })} />)
    expect(container.querySelector('.bg-success')).not.toBeNull()
  })

  it('ai_conversation_turn: info side bar', () => {
    const { container } = render(<EventCard event={mk({ event_type: 'ai_conversation_turn' })} />)
    expect(container.querySelector('.bg-info')).not.toBeNull()
  })

  it('other event_type: border-medium side bar', () => {
    const { container } = render(<EventCard event={mk({ event_type: 'manual_note' })} />)
    expect(container.querySelector('.bg-border-medium')).not.toBeNull()
  })
})
