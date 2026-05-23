/**
 * LlmEgressPanel · T14 LLM egress UI + dry-run preview.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { LlmEgressPanel } from './LlmEgressPanel'
import { api } from '@/lib/api'


// T109 · 包 QueryClientProvider 给 useProviderStatus hook
function renderPanel(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}


describe('LlmEgressPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // 默认 mock providers/status GET (T109 真实数据)
    vi.spyOn(api, 'get').mockResolvedValue({
      data: [
        { name: 'anthropic', models: ['claude-sonnet-4-6'], configured: true, status: 'configured' },
        { name: 'openai', models: ['gpt-4o'], configured: true, status: 'configured' },
        { name: 'minimax', models: ['abab6.5s-chat'], configured: false, status: 'key_missing' },
        { name: 'ollama', models: ['gpt-oss:20b'], configured: true, status: 'configured' },
      ],
    })
  })

  it('renders 3 tier toggles all ENABLED', () => {
    renderPanel(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText('三层出域门禁')).toBeInTheDocument()
    expect(screen.getByText(/实例级 \(instance\)/)).toBeInTheDocument()
    expect(screen.getByText(/项目级 \(project\)/)).toBeInTheDocument()
    expect(screen.getByText(/任务级 \(task\)/)).toBeInTheDocument()
    expect(screen.getAllByText('ENABLED').length).toBe(3)
  })

  it('renders env var labels', () => {
    renderPanel(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText(/INSTANCE_EGRESS_ENABLED/)).toBeInTheDocument()
    expect(screen.getByText(/DEFAULT_PROJECT_EGRESS_ENABLED/)).toBeInTheDocument()
  })

  it('renders 4 provider rows with status badges (T109 真实数据)', async () => {
    renderPanel(<LlmEgressPanel projectId="p1" />)
    // 异步: useQuery 加载完才渲染 rows
    await waitFor(() => {
      expect(screen.getByText('anthropic')).toBeInTheDocument()
      expect(screen.getByText('openai')).toBeInTheDocument()
      expect(screen.getByText('minimax')).toBeInTheDocument()
      expect(screen.getByText('ollama')).toBeInTheDocument()
    })
    // 3 configured + 1 key_missing (来自 beforeEach 的 mock)
    await waitFor(() => {
      expect(screen.getAllByText('已配置').length).toBe(3)
      expect(screen.getByText('未配置 API key')).toBeInTheDocument()
    })
  })

  it('audit section rendered', () => {
    renderPanel(<LlmEgressPanel projectId="p1" />)
    expect(screen.getByText('审计')).toBeInTheDocument()
    expect(screen.getByText('full (完整审计)')).toBeInTheDocument()
  })

  it('preview button visible', () => {
    renderPanel(<LlmEgressPanel projectId="p1" />)
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
    renderPanel(<LlmEgressPanel projectId="p1" />)
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
    renderPanel(<LlmEgressPanel projectId="p1" />)
    fireEvent.click(screen.getByText(/预测 \(task=weekly_report\)/))
    await waitFor(() => expect(screen.getByText('预测失败')).toBeInTheDocument())
  })

  it('preview button disabled when previewing', async () => {
    let resolveFn: ((v: { data: unknown }) => void) | null = null
    vi.spyOn(api, 'post').mockReturnValue(
      new Promise((res) => { resolveFn = res }),
    )
    renderPanel(<LlmEgressPanel projectId="p1" />)
    fireEvent.click(screen.getByText(/预测 \(task=weekly_report\)/))
    await waitFor(() => {
      expect(screen.getByText(/预测 \(task=weekly_report\)/).closest('button')).toBeDisabled()
    })
    resolveFn!({ data: {} })
  })
})
