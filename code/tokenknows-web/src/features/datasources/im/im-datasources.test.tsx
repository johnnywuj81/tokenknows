/**
 * IMDatasourcesPage smoke (v0.3 T24)
 *
 * 覆盖:
 * - 空列表 → 显示 EmptyState
 * - 已有 connection → 渲染卡片 + status badge
 * - 点击 "添加 IM" → 弹出向导
 * - 选择平台 + 点击"获取授权链接" → mutation 调用 + 渲染 authorize_url
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import IMDatasourcesPage from './IMDatasourcesPage'
import type {
  CreateIMConnectionResponse,
  IMConnection,
} from '@/types/api'

const mockHooks = vi.hoisted(() => ({
  useIMConnections: vi.fn(),
  useCreateIMConnection: vi.fn(),
  useRevokeIMConnection: vi.fn(),
}))

vi.mock('./hooks/useIMConnections', () => ({
  useIMConnections: mockHooks.useIMConnections,
  useCreateIMConnection: mockHooks.useCreateIMConnection,
  useRevokeIMConnection: mockHooks.useRevokeIMConnection,
}))


function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/projects/p1/datasources']}>
        <Routes>
          <Route path="/projects/:id/datasources" element={<IMDatasourcesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}


const _make_connection = (overrides: Partial<IMConnection> = {}): IMConnection => ({
  id: 'im-1',
  project_id: 'p1',
  platform: 'feishu',
  tenant_name: 'My Corp',
  auth_token_enc: null,
  refresh_token_enc: null,
  token_expires_at: null,
  consent_signed_by: null,
  consent_user_id: null,
  consent_signed_at: null,
  revoked_at: null,
  status: 'active',
  last_synced_at: null,
  created_at: '2026-05-22T10:00:00Z',
  updated_at: '2026-05-22T10:00:00Z',
  ...overrides,
})


describe('IMDatasourcesPage', () => {
  let mutateAsync: ReturnType<typeof vi.fn>
  let revokeMutate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mutateAsync = vi.fn()
    revokeMutate = vi.fn()
    mockHooks.useCreateIMConnection.mockReturnValue({
      mutateAsync,
      isPending: false,
    })
    mockHooks.useRevokeIMConnection.mockReturnValue({
      mutate: revokeMutate,
      isPending: false,
    })
  })

  it('shows EmptyState when no connections', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText(/还没有 IM 数据源/)).toBeInTheDocument()
  })

  it('renders connection cards', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [
        _make_connection({ id: 'im-1', platform: 'feishu', tenant_name: 'Lark Co' }),
        _make_connection({
          id: 'im-2', platform: 'dingtalk',
          status: 'pending', tenant_name: 'DD Co',
        }),
      ],
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('飞书 / Lark')).toBeInTheDocument()
    expect(screen.getByText('钉钉')).toBeInTheDocument()
    expect(screen.getByText('Lark Co')).toBeInTheDocument()
    expect(screen.getByText('DD Co')).toBeInTheDocument()
  })

  it('opens wizard dialog when "添加 IM" clicked', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /添加 IM/ }))
    expect(screen.getByText(/选择平台/)).toBeInTheDocument()
  })

  it('shows authorize_url after create succeeds', async () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    })
    const resp: CreateIMConnectionResponse = {
      connection: _make_connection({ status: 'pending' }),
      authorize_url: 'https://open.feishu.cn/oauth/authorize?app_id=x',
    }
    mutateAsync.mockResolvedValue(resp)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /添加 IM/ }))
    fireEvent.click(screen.getByRole('button', { name: /获取授权链接/ }))
    await waitFor(() => {
      expect(screen.getByText(/前往 飞书 \/ Lark 授权/)).toBeInTheDocument()
    })
  })

  it('shows warning when authorize_url is config placeholder', async () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    })
    mutateAsync.mockResolvedValue({
      connection: _make_connection({ status: 'pending' }),
      authorize_url: '#im-not-configured:FEISHU_APP_ID 未配置',
    } as CreateIMConnectionResponse)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /添加 IM/ }))
    fireEvent.click(screen.getByRole('button', { name: /获取授权链接/ }))
    await waitFor(() => {
      expect(screen.getByText(/后端凭据未配置/)).toBeInTheDocument()
    })
  })

  it('revokes connection when 撤回 clicked', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: [_make_connection({ id: 'im-x' })],
      isLoading: false,
      isError: false,
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /撤回/ }))
    expect(revokeMutate).toHaveBeenCalledWith('im-x')
  })

  it('shows LoadingSkeleton while loading', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
    const { container } = renderPage()
    // LoadingSkeleton 渲染 Skeleton 组件 (无 testid), 检测渲染了占位 div
    expect(container.querySelector('.animate-pulse, [data-slot="skeleton"]'))
      .not.toBeNull()
    // 业务文案 "添加 IM" 不应出现 (因还在 loading)
    expect(screen.queryByText(/添加 IM/)).not.toBeInTheDocument()
  })

  it('shows ErrorState on error', () => {
    mockHooks.useIMConnections.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    })
    renderPage()
    expect(screen.getByText(/加载 IM 数据源失败/)).toBeInTheDocument()
  })
})
