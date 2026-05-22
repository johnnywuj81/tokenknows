/**
 * Wizard step components · WizardStepper + StepBasicInfo + StepDatasources + StepDone.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WizardStepper } from './WizardStepper'
import { StepBasicInfo } from './StepBasicInfo'
import { StepDatasources } from './StepDatasources'
import { StepDone } from './StepDone'
import type { Datasource, Project } from '@/types/api'


const mockProject: Project = {
  id: 'p1',
  name: 'demo',
  description: '',
  owner_id: 'u1',
  llm_egress_enabled: false,
  task_egress_config: {},
  custom_redaction_terms: [],
  brand_theme: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const mkDs = (overrides: Partial<Datasource> = {}): Datasource => ({
  id: 'd1',
  project_id: 'p1',
  type: 'github',
  name: 'demo repo',
  config: {},
  health: 'healthy',
  last_synced_at: null,
  created_at: new Date().toISOString(),
  ...overrides,
})


// ─── WizardStepper ──────────────────────────────────────────


describe('WizardStepper', () => {
  it('current=1: 4 step labels rendered', () => {
    render(<WizardStepper current={1} />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('选择数据源')).toBeInTheDocument()
    expect(screen.getByText('接入指引')).toBeInTheDocument()
    expect(screen.getByText('完成')).toBeInTheDocument()
  })

  it('current=2: step 1 done (check icon), step 2 active', () => {
    const { container } = render(<WizardStepper current={2} />)
    // step 1 should have checkmark svg (lucide Check)
    const checks = container.querySelectorAll('svg')
    expect(checks.length).toBeGreaterThan(0)
    // step 2 active spans get aria-current="step"
    const activeStep = container.querySelector('[aria-current="step"]')
    expect(activeStep).not.toBeNull()
    expect(activeStep?.textContent).toBe('2')
  })

  it('current=4: 3 separator lines (h-px) rendered', () => {
    const { container } = render(<WizardStepper current={4} />)
    // 3 separator lines: between steps 1-2, 2-3, 3-4
    const lines = container.querySelectorAll('div.h-px')
    expect(lines.length).toBe(3)
  })
})


// ─── StepBasicInfo ──────────────────────────────────────────


describe('StepBasicInfo', () => {
  it('renders inputs with current values', () => {
    render(<StepBasicInfo
      name="my-project"
      description="some desc"
      nameError={null}
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    const nameInput = screen.getByLabelText(/项目名/) as HTMLInputElement
    expect(nameInput.value).toBe('my-project')
  })

  it('calls onChangeName on input', () => {
    const onChangeName = vi.fn()
    render(<StepBasicInfo
      name=""
      description=""
      nameError={null}
      onChangeName={onChangeName}
      onChangeDescription={() => {}}
    />)
    const input = screen.getByLabelText(/项目名/)
    fireEvent.change(input, { target: { value: 'new' } })
    expect(onChangeName).toHaveBeenCalledWith('new')
  })

  it('calls onChangeDescription', () => {
    const onChangeDescription = vi.fn()
    render(<StepBasicInfo
      name=""
      description=""
      nameError={null}
      onChangeName={() => {}}
      onChangeDescription={onChangeDescription}
    />)
    const textarea = screen.getByLabelText(/简介/)
    fireEvent.change(textarea, { target: { value: 'hello' } })
    expect(onChangeDescription).toHaveBeenCalledWith('hello')
  })

  it('shows nameError when present', () => {
    render(<StepBasicInfo
      name="dup"
      description=""
      nameError="项目名重复"
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    expect(screen.getByText('项目名重复')).toBeInTheDocument()
    const input = screen.getByLabelText(/项目名/)
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows help text when no error', () => {
    render(<StepBasicInfo
      name=""
      description=""
      nameError={null}
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    expect(screen.getByText(/2-60 字符/)).toBeInTheDocument()
  })

  it('description char count updates', () => {
    render(<StepBasicInfo
      name=""
      description="hello"
      nameError={null}
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    expect(screen.getByText('5/300')).toBeInTheDocument()
  })

  it('focuses name input when nameError appears', () => {
    const { rerender } = render(<StepBasicInfo
      name=""
      description=""
      nameError={null}
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    rerender(<StepBasicInfo
      name=""
      description=""
      nameError="冲突"
      onChangeName={() => {}}
      onChangeDescription={() => {}}
    />)
    const input = screen.getByLabelText(/项目名/) as HTMLInputElement
    expect(document.activeElement).toBe(input)
  })
})


// ─── StepDatasources ──────────────────────────────────────────


describe('StepDatasources', () => {
  it('renders 5 datasource cards', () => {
    render(<StepDatasources selectedTypes={[]} onToggle={() => {}} />)
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByText('Cursor')).toBeInTheDocument()
    expect(screen.getByText('VS Code')).toBeInTheDocument()
    expect(screen.getByText('本地文件')).toBeInTheDocument()
  })

  it('selected card has aria-pressed=true', () => {
    render(<StepDatasources selectedTypes={['github']} onToggle={() => {}} />)
    const buttons = screen.getAllByRole('button')
    const ghBtn = buttons.find((b) => b.textContent?.includes('GitHub'))
    expect(ghBtn).toHaveAttribute('aria-pressed', 'true')
  })

  it('clicking card invokes onToggle with type', () => {
    const onToggle = vi.fn()
    render(<StepDatasources selectedTypes={[]} onToggle={onToggle} />)
    const buttons = screen.getAllByRole('button')
    const ghBtn = buttons.find((b) => b.textContent?.includes('GitHub'))
    fireEvent.click(ghBtn!)
    expect(onToggle).toHaveBeenCalledWith('github')
  })

  it('recommended badge appears on recommended cards when not selected', () => {
    render(<StepDatasources selectedTypes={[]} onToggle={() => {}} />)
    const badges = screen.getAllByText('推荐')
    // 2 推荐 (claude_code + github)
    expect(badges.length).toBe(2)
  })

  it('recommended badge hidden when selected', () => {
    render(<StepDatasources selectedTypes={['github', 'claude_code']} onToggle={() => {}} />)
    const badges = screen.queryAllByText('推荐')
    expect(badges.length).toBe(0)
  })
})


// ─── StepDone ──────────────────────────────────────────


describe('StepDone', () => {
  it('renders project name in success banner', () => {
    render(<StepDone
      project={mockProject}
      addedDatasources={[]}
      onGoToWorkbench={() => {}}
    />)
    expect(screen.getByText(/项目"demo"创建成功/)).toBeInTheDocument()
  })

  it('lists added datasources', () => {
    render(<StepDone
      project={mockProject}
      addedDatasources={[
        mkDs({ id: 'd1', type: 'github', name: 'org/repo' }),
        mkDs({ id: 'd2', type: 'claude_code', name: 'cc-plugin' }),
      ]}
      onGoToWorkbench={() => {}}
    />)
    expect(screen.getByText('已接入数据源 · 2')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('org/repo')).toBeInTheDocument()
    expect(screen.getByText('cc-plugin')).toBeInTheDocument()
  })

  it('falls back to raw type if unknown', () => {
    render(<StepDone
      project={mockProject}
      addedDatasources={[mkDs({ type: 'unknown_type' as Datasource['type'], name: 'x' })]}
      onGoToWorkbench={() => {}}
    />)
    expect(screen.getByText('unknown_type')).toBeInTheDocument()
  })

  it('does not render datasource list when empty', () => {
    render(<StepDone
      project={mockProject}
      addedDatasources={[]}
      onGoToWorkbench={() => {}}
    />)
    expect(screen.queryByText(/已接入数据源/)).toBeNull()
  })

  it('CTA invokes callback', () => {
    const onGo = vi.fn()
    render(<StepDone
      project={mockProject}
      addedDatasources={[]}
      onGoToWorkbench={onGo}
    />)
    fireEvent.click(screen.getByText(/进入工作台/))
    expect(onGo).toHaveBeenCalled()
  })
})
