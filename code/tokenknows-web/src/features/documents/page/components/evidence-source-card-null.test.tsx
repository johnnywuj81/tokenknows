/**
 * EvidenceSourceCard 分支 · trust/citation null + formatOccurredAt catch.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EvidenceSourceCard } from './EvidenceSourceCard'
import type { Evidence } from '@/types/api'


const mk = (overrides: Partial<Evidence> = {}): Evidence => ({
  id: 'ev1', chapter_id: 'c1', event_id: 'e1', event_version: 1,
  span_start: 0, span_end: 10, citation_text: '[1]',
  manually_added: false, stale: false,
  trust_score: 0.85, citation_strength: 0.7,
  event_preview: {
    event_id: 'e1', title: 'PR',
    source_type: 'github', source_ref: 'a/b#1',
    author_name: 'A', author_email: null,
    occurred_at: new Date().toISOString(),
    content_excerpt: 'x', external_url: null,
  },
  ...overrides,
})


describe('EvidenceSourceCard null branches', () => {
  it('null trust_score: no trust badge', () => {
    render(<EvidenceSourceCard evidence={mk({ trust_score: null })} />)
    expect(screen.queryByText('trust')).toBeNull()
  })

  it('null citation_strength: no citation badge', () => {
    render(<EvidenceSourceCard evidence={mk({ citation_strength: null })} />)
    expect(screen.queryByText('citation')).toBeNull()
  })

  it('both null: only manually_added/stale conditional badges remain', () => {
    render(<EvidenceSourceCard evidence={mk({
      trust_score: null, citation_strength: null,
      manually_added: false, stale: false,
    })} />)
    expect(screen.queryByText('trust')).toBeNull()
    expect(screen.queryByText('citation')).toBeNull()
  })
})


describe('EvidenceSourceCard formatOccurredAt catch', () => {
  let originalToLocale: typeof Date.prototype.toLocaleString
  beforeEach(() => {
    originalToLocale = Date.prototype.toLocaleString
    Date.prototype.toLocaleString = vi.fn(() => {
      throw new Error('boom')
    }) as unknown as typeof Date.prototype.toLocaleString
  })
  afterEach(() => {
    Date.prototype.toLocaleString = originalToLocale
  })

  it('toLocaleString throws: falls back to raw iso', () => {
    render(<EvidenceSourceCard evidence={mk({
      event_preview: { ...mk().event_preview, occurred_at: '2026-01-15T10:00:00Z' },
    })} />)
    expect(screen.getByText(/2026-01-15T10:00:00Z/)).toBeInTheDocument()
  })
})
