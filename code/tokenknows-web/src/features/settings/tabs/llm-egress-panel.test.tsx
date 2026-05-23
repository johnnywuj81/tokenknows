/**
 * LlmEgressPanel · T14 LLM egress UI + dry-run preview.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LlmEgressPanel } from './LlmEgressPanel'
import { api } from '@/lib/api'


describe('LlmEgressPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders 3 tier toggles all ENABLED', () => {
    render(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText('三层出域门禁')).toBeInTheDocument()
    expect(screen.getByText(/实例级 \(instance\)/)).toBeInTheDocument()
    expect(screen.getByText(/项目级 \(project\)/)).toBeInTheDocument()
    expect(screen.getByText(/任务级 \(task\)/)).toBeInTheDocument()
    expect(screen.getAllByText('ENABLED').length).toBe(3)
  })

  it('renders env var labels', () => {
    render(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText(/INSTANCE_EGRESS_ENABLED/)).toBeInTheDocument()
    expect(screen.getByText(/DEFAULT_PROJECT_EGRESS_ENABLED/)).toBeInTheDocument()
  })

  it('renders 4 provider rows with status badges', () => {
    render(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText('anthropic')).toBeInTheDocument()
    expect(screen.getByText('openai')).toBeInTheDocument()
    expect(screen.getByText('minimax')).toBeInTheDocument()
    expect(screen.getByText('ollama')).toBeInTheDocument()
    expect(screen.getByText('在线')).toBeInTheDocument()
    expect(screen.getByText('Key 无效')).toBeInTheDocument()
    expect(screen.getAllByText('本机网络不通').length).toBe(2)
  })

  it('audit section rendered', () => {
    render(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText('审计')).toBeInTheDocument()
    expect(screen.getByText('full (完整审计)')).toBeInTheDocument()
  })

  it('preview button visible', () => {
    render(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText(/预测 \(task=weekly_report\)/)).toBeInTheDocument()
  })

  it('preview success: renders JSON output', async () => {
    const mockPreview = {
      will_send: true,
      provider: 'anthropic',
      model: 'claude-sonnet-4-6',
      estimated_input_tokens: 1000,
      estimated_output_tokens: 500,
      egress_check: { instance: true, project: true, task: true, all_pass: true },
    }
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: mockPreview })
    render(<LlmEgressPanel projectId="p1" />)
    fireEvent.click(screen.getByText(/预测 \(task=weekly_report\)/))
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/llm/egress/preview',
        expect.objectContaining({
          task: 'weekly_report',
          project_id: 'p1',
        }),
      )
      expect(screen.getByText(/"will_send": true/)).toBeInTheDocument()
      expect(screen.getByText(/"provider": "anthropic"/)).toBeInTheDocument()
    })
  })

  it('preview error: displays error message', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('预测失败'))
    render(<LlmEgressPanel projectId="p1" />)
    fireEvent.click(screen.getByText(/预测 \(task=weekly_report\)/))
    await waitFor(() => expect(screen.getByText('预测失败')).toBeInTheDocument())
  })

  it('preview button disabled when previewing', async () => {
    let resolveFn: ((v: { data: unknown }) => void) | null = null
    vi.spyOn(api, 'post').mockReturnValue(
      new Promise((res) => { resolveFn = res }),
    )
    render(<LlmEgressPanel projectId="p1" />)
    fireEvent.click(screen.getByText(/预测 \(task=weekly_report\)/))
    await waitFor(() => {
      expect(screen.getByText(/预测 \(task=weekly_report\)/).closest('button')).toBeDisabled()
    })
    resolveFn!({ data: {} })
  })
})
