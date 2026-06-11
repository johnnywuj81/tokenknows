/**
 * McpAccessPanel · Phase B unit tests.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { McpAccessPanel } from './McpAccessPanel'
import type { ApiTokenPublic } from '@/types/api'

const mock = new MockAdapter(api)

function _render(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function _setUser(id: string) {
  useAuthStore.setState({
    user: {
      id,
      email: `${id}@x`,
      display_name: id,
      is_instance_admin: false,
      email_verified_at: null,
      created_at: '',
      updated_at: '',
    },
    accessToken: 'fake',
    isAuthenticated: true,
  })
}

const mkToken = (overrides: Partial<ApiTokenPublic> = {}): ApiTokenPublic => ({
  id: 't-1',
  name: 'my-macbook',
  token_prefix: 'tkk_abcd',
  created_at: '2026-06-01T00:00:00Z',
  last_used_at: null,
  ...overrides,
})

beforeEach(() => {
  mock.reset()
  _setUser('ou-alice')
})

afterEach(() => {
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false })
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('McpAccessPanel', () => {
  it('空列表 → empty-state CTA + 复制按钮 disabled', async () => {
    mock.onGet('/me/tokens').reply(200, { items: [] })
    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('tokens-empty')).toBeInTheDocument(),
    )
    expect(screen.getByText('创建第一个 API token')).toBeInTheDocument()
    // 没有明文在手 → 复制配置 disabled
    expect(screen.getByTestId('copy-env-btn')).toBeDisabled()
  })

  it('创建 → POST 201 → 明文可见 + env 块含三行 TOKENKNOWS_ + 复制串正确', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...window.navigator, clipboard: { writeText } })

    const plain = 'tkk_abcd_PLAINTEXT_ONLY_ONCE_9f8e7d6c'
    mock.onGet('/me/tokens').reply(200, { items: [] })
    mock.onPost('/me/tokens').reply(201, {
      token: plain,
      item: mkToken({ id: 't-new', name: 'ci-runner' }),
    })

    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('create-token-form')).toBeInTheDocument(),
    )
    fireEvent.change(screen.getByTestId('create-token-name'), {
      target: { value: 'ci-runner' },
    })
    fireEvent.click(screen.getByTestId('create-token-submit'))

    // 一次性明文卡 + amber 警告
    await waitFor(() =>
      expect(screen.getByTestId('token-reveal')).toBeInTheDocument(),
    )
    expect(
      screen.getByText('token 只显示这一次, 请立即复制'),
    ).toBeInTheDocument()
    // TokenDisplay 默认遮蔽; 点眼睛后明文可见
    fireEvent.click(screen.getByLabelText('显示 token'))
    expect(screen.getByText(plain)).toBeInTheDocument()

    // POST body 校验
    const body = JSON.parse(mock.history.post[0].data)
    expect(body.name).toBe('ci-runner')

    // env 块: 恰好三行 TOKENKNOWS_, token 行用明文
    const envText = screen.getByTestId('env-block').textContent ?? ''
    const lines = envText.split('\n')
    expect(lines).toHaveLength(3)
    const apiBase = (
      screen.getByTestId('env-api-base') as HTMLInputElement
    ).value
    expect(lines[0]).toBe(`TOKENKNOWS_API_BASE=${apiBase}`)
    expect(lines[1]).toBe(`TOKENKNOWS_API_TOKEN=${plain}`)
    expect(lines[2]).toBe('TOKENKNOWS_DEFAULT_PROJECT=p-1')

    // 复制配置: 明文在手 → enabled, 复制串 = env 块全文
    const copyBtn = screen.getByTestId('copy-env-btn')
    expect(copyBtn).toBeEnabled()
    fireEvent.click(copyBtn)
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(envText))
  })

  it('列表渲染前缀, 永不出现完整 token', async () => {
    mock.onGet('/me/tokens').reply(200, {
      items: [
        mkToken(),
        mkToken({
          id: 't-2',
          name: 'ci-runner',
          token_prefix: 'tkk_ef01',
          last_used_at: '2026-06-10T08:00:00Z',
        }),
      ],
    })
    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('tokens-table')).toBeInTheDocument(),
    )
    expect(screen.getByText('tkk_abcd')).toBeInTheDocument()
    expect(screen.getByText('tkk_ef01')).toBeInTheDocument()
    // last_used_at: null → 从未使用
    expect(screen.getByText('从未使用')).toBeInTheDocument()
    // 没有任何完整 token (前缀外更长的 tkk_ 串) 渲染出来
    expect(screen.queryByText(/tkk_[A-Za-z0-9_]{10,}/)).toBeNull()
    // env 块没明文 → 占位
    expect(screen.getByTestId('env-block').textContent).toContain(
      'TOKENKNOWS_API_TOKEN=tkk_********',
    )
  })

  it('撤销 → confirm → DELETE 204 → 列表 invalidate (GET 重发)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.onGet('/me/tokens').reply(200, { items: [mkToken()] })
    mock.onDelete('/me/tokens/t-1').reply(204)
    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('token-row-t-1')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('revoke-t-1'))
    await waitFor(() => expect(mock.history.delete.length).toBe(1))
    expect(window.confirm).toHaveBeenCalled()
    // mutation onSuccess invalidate → GET 重发 (初始 1 次 + 重发 ≥ 1 次)
    await waitFor(() =>
      expect(
        mock.history.get.filter((g) => g.url === '/me/tokens').length,
      ).toBeGreaterThanOrEqual(2),
    )
  })

  it('confirm 取消 → 不发 DELETE', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mock.onGet('/me/tokens').reply(200, { items: [mkToken()] })
    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByTestId('token-row-t-1')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('revoke-t-1'))
    expect(mock.history.delete.length).toBe(0)
  })

  it('GET 500 → error 状态 + 重试', async () => {
    mock.onGet('/me/tokens').reply(500)
    _render(<McpAccessPanel projectId="p-1" />)
    await waitFor(() =>
      expect(screen.getByText(/加载 API token 失败/)).toBeInTheDocument(),
    )
    expect(screen.getByText('重试')).toBeInTheDocument()
  })
})
