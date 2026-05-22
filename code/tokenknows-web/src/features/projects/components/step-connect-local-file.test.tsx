/**
 * StepConnect local_file onSkip 分支 · 点击 "稍后上传" 触发 no-op callback.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { StepConnect } from './StepConnect'
import type { Project } from '@/types/api'


const mockProject: Project = {
  id: 'p1', name: 'demo', description: '', owner_id: 'u1',
  llm_egress_enabled: false, task_egress_config: {},
  custom_redaction_terms: [], brand_theme: {},
  created_at: '', updated_at: '',
}


function withQuery(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}


describe('StepConnect local_file onSkip', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('clicking 稍后上传 fires onSkip no-op (no crash)', () => {
    render(withQuery(<StepConnect
      project={mockProject}
      selectedTypes={['local_file']}
      addedDatasources={[]}
      onDatasourceAdded={() => {}}
    />))
    expect(() => fireEvent.click(screen.getByText(/稍后上传/))).not.toThrow()
  })
})
