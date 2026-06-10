/**
 * T130.4 · MembersPanel · ImBindingCell 自助绑定/解绑飞书 open_id.
 *
 * 覆盖:
 *  - 非自己 + 非 owner → 只读展示 (隐藏 open_id 值, 仅 已绑定/—)
 *  - 自己: 看到 "未绑定" + "绑定" 按钮
 *  - 点 "绑定" → 出 input + "存"/"取消"
 *  - "存" → 触发 PATCH /im-binding 调用 + refetch
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MockAdapter from 'axios-mock-adapter'
import type { ReactNode } from 'react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { MembersPanel } from './MembersPanel'
import type { ProjectMember } from '@/types/api'


const mock = new MockAdapter(api)


function _wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}


function _mkMember(overrides: Partial<ProjectMember> = {}): ProjectMember {
  return {
    id: 'm-1',
    project_id: 'p1',
    user_id: 'alice@example.com',
    role: 'contributor',
    added_by: 'ou-owner',
    added_at: '2026-05-01T00:00:00Z',
    note: null,
    im_feishu_open_id: null,
    ...overrides,
  }
}


function _stubMembers(items: ProjectMember[]) {
  mock.onGet('/projects/p1/members').reply(200, {
    project_id: 'p1',
    items,
    owner_count: items.filter((m) => m.role === 'owner').length,
    reviewer_count: items.filter((m) => m.role === 'reviewer').length,
    contributor_count: items.filter((m) => m.role === 'contributor').length,
  })
}


describe('MembersPanel · T130.4 ImBindingCell', () => {
  beforeEach(() => {
    mock.reset()
  })
  afterEach(() => {
    mock.reset()
    useAuthStore.setState({ user: null, accessToken: null })
  })

  it('自己: 未绑定 → 显示 "未绑定" + "绑定" 按钮', async () => {
    useAuthStore.setState({
      user: { id: 'alice@example.com', email: 'alice@example.com', display_name: 'Alice' } as never,
      accessToken: 't',
    })
    _stubMembers([
      _mkMember({ user_id: 'ou-owner', role: 'owner' }),
      _mkMember(),
    ])
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MembersPanel projectId="p1" />, { wrapper: _wrapper(qc) })
    await waitFor(() =>
      expect(screen.getByTestId('im-binding-display-alice@example.com'))
        .toHaveTextContent('未绑定'),
    )
    expect(
      screen.getByTestId('im-binding-edit-alice@example.com'),
    ).toHaveTextContent('绑定')
  })

  it('自己: 已绑定 → 显示 open_id + "编辑" 按钮', async () => {
    useAuthStore.setState({
      user: { id: 'alice@example.com', email: 'a@x.com', display_name: 'A' } as never,
      accessToken: 't',
    })
    _stubMembers([
      _mkMember({ user_id: 'ou-owner', role: 'owner' }),
      _mkMember({ im_feishu_open_id: 'ou_alice_bound' }),
    ])
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MembersPanel projectId="p1" />, { wrapper: _wrapper(qc) })
    await waitFor(() =>
      expect(
        screen.getByTestId('im-binding-display-alice@example.com'),
      ).toHaveTextContent('ou_alice_bound'),
    )
    expect(
      screen.getByTestId('im-binding-edit-alice@example.com'),
    ).toHaveTextContent('编辑')
  })

  it('点"绑定" → 显示 input + "存" 按钮 + 保存触发 PATCH', async () => {
    useAuthStore.setState({
      user: { id: 'alice@example.com', email: 'a@x.com', display_name: 'A' } as never,
      accessToken: 't',
    })
    _stubMembers([
      _mkMember({ user_id: 'ou-owner', role: 'owner' }),
      _mkMember(),
    ])
    mock
      .onPatch('/projects/p1/members/alice@example.com/im-binding')
      .reply(200, _mkMember({ im_feishu_open_id: 'ou_alice_new' }))

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MembersPanel projectId="p1" />, { wrapper: _wrapper(qc) })
    await waitFor(() =>
      screen.getByTestId('im-binding-edit-alice@example.com'),
    )

    fireEvent.click(screen.getByTestId('im-binding-edit-alice@example.com'))
    const input = await screen.findByTestId(
      'im-binding-input-alice@example.com',
    )
    fireEvent.change(input, { target: { value: 'ou_alice_new' } })
    fireEvent.click(screen.getByTestId('im-binding-save-alice@example.com'))

    await waitFor(() => {
      const patchCalls = mock.history.patch.filter((c) =>
        c.url?.includes('/im-binding'),
      )
      expect(patchCalls).toHaveLength(1)
      expect(JSON.parse(patchCalls[0].data)).toEqual({
        im_feishu_open_id: 'ou_alice_new',
      })
    })
  })

  it('保存空字符串 → PATCH body im_feishu_open_id=null (解绑)', async () => {
    useAuthStore.setState({
      user: { id: 'alice@example.com', email: 'a@x.com', display_name: 'A' } as never,
      accessToken: 't',
    })
    _stubMembers([
      _mkMember({ user_id: 'ou-owner', role: 'owner' }),
      _mkMember({ im_feishu_open_id: 'ou_alice_was_bound' }),
    ])
    mock
      .onPatch('/projects/p1/members/alice@example.com/im-binding')
      .reply(200, _mkMember({ im_feishu_open_id: null }))

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MembersPanel projectId="p1" />, { wrapper: _wrapper(qc) })
    await waitFor(() =>
      screen.getByTestId('im-binding-edit-alice@example.com'),
    )
    fireEvent.click(screen.getByTestId('im-binding-edit-alice@example.com'))
    const input = await screen.findByTestId(
      'im-binding-input-alice@example.com',
    )
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.click(screen.getByTestId('im-binding-save-alice@example.com'))

    await waitFor(() => {
      const patchCalls = mock.history.patch.filter((c) =>
        c.url?.includes('/im-binding'),
      )
      expect(patchCalls).toHaveLength(1)
      expect(JSON.parse(patchCalls[0].data)).toEqual({
        im_feishu_open_id: null,
      })
    })
  })

  it('其他成员 (非自己非 owner) → 只读 "已绑定" / "—", 无 edit 按钮', async () => {
    // 我是 carol (contributor), 看 alice 的行
    useAuthStore.setState({
      user: { id: 'carol@example.com', email: 'c@x.com', display_name: 'C' } as never,
      accessToken: 't',
    })
    _stubMembers([
      _mkMember({ id: 'm-owner', user_id: 'ou-owner', role: 'owner' }),
      _mkMember({ id: 'm-alice', im_feishu_open_id: 'ou_alice_xxxx_PRIVATE' }),
      _mkMember({ id: 'm-carol', user_id: 'carol@example.com' }),
    ])
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MembersPanel projectId="p1" />, { wrapper: _wrapper(qc) })
    await waitFor(() => screen.getByText('alice@example.com'))
    // alice 的 open_id 不应在屏幕上 (隐私 — 仅显示"已绑定")
    expect(screen.queryByText('ou_alice_xxxx_PRIVATE')).not.toBeInTheDocument()
    // alice 行不应有 edit 按钮 (我是 carol, 非 owner)
    expect(
      screen.queryByTestId('im-binding-edit-alice@example.com'),
    ).not.toBeInTheDocument()
  })
})
