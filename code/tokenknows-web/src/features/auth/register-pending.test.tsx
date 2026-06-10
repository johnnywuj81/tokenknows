/**
 * RegisterPage · 提交 pending state · 按钮 "注册中..." 文案分支.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import RegisterPage from './RegisterPage'
import { api } from '@/lib/api'


function withWrappers(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter initialEntries={['/register']}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}


describe('RegisterPage pending state', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows 注册中... while mutation is pending', async () => {
    // 初始化为 no-op 避免 TS 把闭包内赋值的变量窄化成 null (TS2349)
    let resolveFn: (v: unknown) => void = () => {}
    vi.spyOn(api, 'post').mockReturnValueOnce(
      new Promise((res) => { resolveFn = res }),
    )
    render(withWrappers(<RegisterPage />))
    fireEvent.change(screen.getByLabelText(/邮箱/), {
      target: { value: 'new@example.com' },
    })
    const inputs = screen.getAllByLabelText(/.*/i)
    // 找到 display_name 字段 - 通常显示在第 2 个 input
    const allInputs = document.querySelectorAll('input')
    fireEvent.change(allInputs[0], { target: { value: 'new@example.com' } })
    fireEvent.change(allInputs[1], { target: { value: 'Alice' } })
    fireEvent.change(allInputs[2], { target: { value: 'StrongPw!123' } })
    void inputs
    const submitBtn = screen.getAllByText('注册').find((b) => b.tagName === 'BUTTON')
    fireEvent.click(submitBtn!)
    await waitFor(() => expect(screen.getByText(/注册中/)).toBeInTheDocument())
    resolveFn({ data: { id: 'u1', email: 'new@example.com' } })
  })
})
