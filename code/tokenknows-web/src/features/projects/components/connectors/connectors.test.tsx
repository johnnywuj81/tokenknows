/**
 * Connectors 测试 · ConnectorCard + TokenDisplay + PluginConnector
 *                 + GitHubConnector + LocalFileConnector.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Sparkles } from 'lucide-react'
import { ConnectorCard } from './ConnectorCard'
import { TokenDisplay } from '@/components/shared/TokenDisplay'
import { PluginConnector } from './PluginConnector'
import { GitHubConnector } from './GitHubConnector'
import { LocalFileConnector } from './LocalFileConnector'
import type { Datasource } from '@/types/api'


const mkDs = (overrides: Partial<Datasource> = {}): Datasource => ({
  id: 'd1',
  project_id: 'p1',
  type: 'claude_code',
  name: 'plugin',
  config: {},
  health: 'healthy',
  last_synced_at: null,
  created_at: new Date().toISOString(),
  ...overrides,
})


// ─── ConnectorCard ─────────────────────────────────────────


describe('ConnectorCard', () => {
  it('renders title + state badge (pending)', () => {
    render(<ConnectorCard icon={Sparkles} title="标题" state="pending">
      <p>body</p>
    </ConnectorCard>)
    expect(screen.getByText('标题')).toBeInTheDocument()
    expect(screen.getByText('待配置')).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('connected state shows 已连接 + success border', () => {
    const { container } = render(<ConnectorCard icon={Sparkles} title="t" state="connected">
      <span>x</span>
    </ConnectorCard>)
    expect(screen.getByText('已连接')).toBeInTheDocument()
    expect(container.querySelector('.border-success-border')).not.toBeNull()
  })

  it('in_progress state shows spinner + 配置中', () => {
    render(<ConnectorCard icon={Sparkles} title="t" state="in_progress"><span>x</span></ConnectorCard>)
    expect(screen.getByText('配置中')).toBeInTheDocument()
  })

  it('failed state shows 失败', () => {
    render(<ConnectorCard icon={Sparkles} title="t" state="failed"><span>x</span></ConnectorCard>)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })
})


// ─── TokenDisplay ─────────────────────────────────────────


describe('TokenDisplay', () => {
  beforeEach(() => {
    // mock clipboard
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('default visible=false: long token shows 前 12 字符 + 16 个 •', () => {
    render(<TokenDisplay token="head.MIDDLE_LONG_SECRET.tail" />)
    // 应展示 mask (前 12 字符 + 16 个 •), 不展示明文
    expect(screen.queryByText('head.MIDDLE_LONG_SECRET.tail')).toBeNull()
    expect(screen.getByText(`head.MIDDLE_${'•'.repeat(16)}`)).toBeInTheDocument()
    expect(screen.getByLabelText('显示 token')).toBeInTheDocument()
  })

  it('default visible=false: short token (≤16 字符) 全遮蔽', () => {
    render(<TokenDisplay token="abc.def.ghi" />)
    expect(screen.queryByText('abc.def.ghi')).toBeNull()
    expect(screen.getByText('•'.repeat(16))).toBeInTheDocument()
  })

  it('clicking eye reveals plain token', () => {
    render(<TokenDisplay token="abc.def.ghi" />)
    fireEvent.click(screen.getByLabelText('显示 token'))
    expect(screen.getByText('abc.def.ghi')).toBeInTheDocument()
    expect(screen.getByLabelText('隐藏 token')).toBeInTheDocument()
  })

  it('clicking copy invokes clipboard.writeText + shows 已复制', async () => {
    render(<TokenDisplay token="X.Y.Z" />)
    fireEvent.click(screen.getByLabelText('复制 token'))
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('X.Y.Z')
      expect(screen.getByText('已复制')).toBeInTheDocument()
    })
  })

  it('clipboard error falls back to execCommand', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    })
    const execSpy = vi.fn().mockReturnValue(true)
    Object.assign(document, { execCommand: execSpy })
    render(<TokenDisplay token="X.Y.Z" />)
    fireEvent.click(screen.getByLabelText('复制 token'))
    await waitFor(() => {
      expect(execSpy).toHaveBeenCalledWith('copy')
    })
  })

  it('custom label', () => {
    render(<TokenDisplay token="a.b.c" label="API key" />)
    expect(screen.getByText('API key')).toBeInTheDocument()
  })
})


// ─── PluginConnector ─────────────────────────────────────


describe('PluginConnector', () => {
  it('pending state: 生成 button visible', () => {
    render(<PluginConnector
      type="claude_code"
      datasource={undefined}
      isPending={false}
      onCreate={() => {}}
    />)
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('生成连接 token')).toBeInTheDocument()
  })

  it('isPending: button shows 生成中... + disabled', () => {
    render(<PluginConnector
      type="claude_code"
      datasource={undefined}
      isPending={true}
      onCreate={() => {}}
    />)
    const btn = screen.getByRole('button', { name: /生成中/ })
    expect(btn).toBeDisabled()
  })

  it('click 生成 invokes onCreate', () => {
    const onCreate = vi.fn()
    render(<PluginConnector
      type="cursor"
      datasource={undefined}
      isPending={false}
      onCreate={onCreate}
    />)
    fireEvent.click(screen.getByText('生成连接 token'))
    expect(onCreate).toHaveBeenCalled()
  })

  it('connected state: renders install command + TokenDisplay', () => {
    render(<PluginConnector
      type="vscode"
      datasource={mkDs({ type: 'vscode', connection_token: 'tk.eyJ.sig' })}
      isPending={false}
      onCreate={() => {}}
    />)
    expect(screen.getByText('已连接')).toBeInTheDocument()
    expect(screen.getByText(/code --install-extension/)).toBeInTheDocument()
    expect(screen.getByLabelText(/显示 token/)).toBeInTheDocument()
  })

  it('connected: 完整文档 link rendered', () => {
    render(<PluginConnector
      type="claude_code"
      datasource={mkDs({ connection_token: 'a.b.c' })}
      isPending={false}
      onCreate={() => {}}
    />)
    const link = screen.getByText(/完整文档/)
    expect(link).toHaveAttribute('href', expect.stringContaining('claude-code'))
  })
})


// ─── GitHubConnector ─────────────────────────────────────


describe('GitHubConnector', () => {
  it('pending: PAT + repos form rendered', () => {
    render(<GitHubConnector
      datasource={undefined}
      isPending={false}
      error={null}
      onSubmit={() => {}}
    />)
    expect(screen.getByLabelText(/Personal Access Token/)).toBeInTheDocument()
    expect(screen.getByLabelText(/仓库/)).toBeInTheDocument()
  })

  it('submit calls onSubmit with parsed repos (newline + comma)', () => {
    const onSubmit = vi.fn()
    render(<GitHubConnector
      datasource={undefined}
      isPending={false}
      error={null}
      onSubmit={onSubmit}
    />)
    fireEvent.change(screen.getByLabelText(/Personal Access Token/), {
      target: { value: 'ghp_abc' },
    })
    fireEvent.change(screen.getByLabelText(/仓库/), {
      target: { value: 'a/b\nc/d, e/f\n  ' },
    })
    fireEvent.click(screen.getByText('校验并接入'))
    expect(onSubmit).toHaveBeenCalledWith({
      pat: 'ghp_abc',
      repos: ['a/b', 'c/d', 'e/f'],
    })
  })

  it('submit button disabled when PAT empty', () => {
    render(<GitHubConnector
      datasource={undefined}
      isPending={false}
      error={null}
      onSubmit={() => {}}
    />)
    expect(screen.getByText('校验并接入')).toBeDisabled()
  })

  it('isPending: shows 校验中... and disabled', () => {
    render(<GitHubConnector
      datasource={undefined}
      isPending={true}
      error={null}
      onSubmit={() => {}}
    />)
    expect(screen.getByRole('button', { name: /校验中/ })).toBeDisabled()
  })

  it('renders ApiError message when error passed', () => {
    const apiErr = Object.assign(new Error('PAT 无效'), {
      code: 'INVALID_PAT',
      status: 400,
    })
    render(<GitHubConnector
      datasource={undefined}
      isPending={false}
      error={apiErr}
      onSubmit={() => {}}
    />)
    expect(screen.getByText('PAT 无效')).toBeInTheDocument()
  })

  it('connected: shows repo count from config', () => {
    render(<GitHubConnector
      datasource={mkDs({ type: 'github', config: { repos: ['a/b', 'c/d', 'e/f'] } })}
      isPending={false}
      error={null}
      onSubmit={() => {}}
    />)
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText(/已接入/)).toBeInTheDocument()
  })

  it('connected with non-array repos config: shows 0', () => {
    render(<GitHubConnector
      datasource={mkDs({ type: 'github', config: {} })}
      isPending={false}
      error={null}
      onSubmit={() => {}}
    />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})


// ─── LocalFileConnector ───────────────────────────────────


describe('LocalFileConnector', () => {
  it('renders skip button + invokes onSkip', () => {
    const onSkip = vi.fn()
    render(<LocalFileConnector onSkip={onSkip} />)
    expect(screen.getByText('本地文件')).toBeInTheDocument()
    fireEvent.click(screen.getByText(/稍后上传/))
    expect(onSkip).toHaveBeenCalled()
  })
})
