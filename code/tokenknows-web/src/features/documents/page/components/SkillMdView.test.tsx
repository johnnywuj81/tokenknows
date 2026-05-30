/**
 * SkillMdView · 渲染测试
 *
 * 覆盖:
 * - 标准 SKILL.md (frontmatter + body) 正确解析
 * - frontmatter 缺失/破损时 fallback (显示 raw + 错误提示)
 * - MCP 工具 chip 与内置工具 chip 视觉区分 (class 不同)
 * - body 里的 `---` (markdown hr) 不会被误识为 frontmatter close
 */

import { render, screen, within } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

import { SkillMdView } from './SkillMdView'

const STANDARD_SKILL_MD = `---
name: docker-prod-deploy
description: docker compose 生产环境部署 SOP, 修改 backend 后必须 build + force-recreate
triggers:
  - docker compose deploy
  - prod build force-recreate
  - 生产部署
allowed-tools: Bash, Read, mcp__github__create_pull_request_review
scope: project
category: engineering
---

## 适用场景
- 修改 backend 代码后推到 prod

## 关键步骤
1. **拉新代码** (use \`Bash\`): \`git pull origin main\`

## 好例子 / 坏例子
坏: 只 restart → 容器仍跑旧代码
好: build + force-recreate
`

describe('SkillMdView', () => {
  it('parses standard frontmatter and renders structured fields', () => {
    render(<SkillMdView content={STANDARD_SKILL_MD} />)
    const meta = screen.getByLabelText('skill metadata')
    const inMeta = within(meta)

    // name shown as code
    expect(inMeta.getByText('docker-prod-deploy')).toBeInTheDocument()

    // description shown
    expect(
      inMeta.getByText(/docker compose 生产环境部署 SOP/),
    ).toBeInTheDocument()

    // triggers shown as chips
    expect(inMeta.getByText('docker compose deploy')).toBeInTheDocument()
    expect(inMeta.getByText('生产部署')).toBeInTheDocument()

    // allowed-tools chips (scoped to metadata, since body also contains `Bash` in code)
    expect(inMeta.getByText('Bash')).toBeInTheDocument()
    expect(inMeta.getByText('Read')).toBeInTheDocument()
    expect(
      inMeta.getByText('mcp__github__create_pull_request_review'),
    ).toBeInTheDocument()
  })

  it('renders body markdown headers (not raw `##`)', () => {
    render(<SkillMdView content={STANDARD_SKILL_MD} />)
    // markdown-it should convert ## to <h2>
    const headers = screen.getAllByRole('heading', { level: 2 })
    const headerTexts = headers.map((h) => h.textContent)
    expect(headerTexts).toEqual(
      expect.arrayContaining(['适用场景', '关键步骤', '好例子 / 坏例子']),
    )
  })

  it('marks MCP tools with different styling than built-in tools', () => {
    render(<SkillMdView content={STANDARD_SKILL_MD} />)
    const meta = screen.getByLabelText('skill metadata')
    const inMeta = within(meta)
    const mcpChip = inMeta.getByText('mcp__github__create_pull_request_review')
    const bashChip = inMeta.getByText('Bash')
    expect(mcpChip.getAttribute('title')).toBe('MCP 工具')
    expect(bashChip.getAttribute('title')).toBe('内置工具')
  })

  it('shows error banner when frontmatter delimiter missing', () => {
    const broken = '# No frontmatter here\n\nJust body content.'
    render(<SkillMdView content={broken} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/no frontmatter/)
  })

  it('shows backend parse error when provided', () => {
    render(
      <SkillMdView
        content={STANDARD_SKILL_MD}
        backendParseError="missing 'name' field"
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/missing 'name' field/)
  })

  it('does NOT split on `---` appearing inside body', () => {
    const withHrInBody = `---
name: skill-with-hr
description: test
---

## Section 1
some content

---

## Section 2
more content
`
    render(<SkillMdView content={withHrInBody} />)
    // body should contain Section 2 (proves close-delim is the SECOND `---`,
    // not a body `---` further down)
    expect(screen.getByText('Section 2')).toBeInTheDocument()
    expect(screen.getByText('skill-with-hr')).toBeInTheDocument()
  })

  it('recovers from LLM wrapping output in ```markdown fence', () => {
    // MiniMax / GPT-3.5 抽风的输出形态
    const polluted = `\`\`\`markdown
---
name: docker-prod-deploy
description: 用于在生产环境中部署 Docker 应用。
triggers:
  - docker 部署
  - 生产环境
allowed-tools: Bash, Read, Edit
scope: project
category: engineering
---

## 适用场景
- 当需要在生产环境中部署新的 Docker 容器时
\`\`\``
    const { container } = render(<SkillMdView content={polluted} />)
    // 不应有 error banner
    expect(container.querySelector('[role="alert"]')).toBeNull()
    // 元数据正常显示
    const meta = screen.getByLabelText('skill metadata')
    expect(within(meta).getByText('docker-prod-deploy')).toBeInTheDocument()
    expect(within(meta).getByText('Bash')).toBeInTheDocument()
    // body markdown 也正常渲染
    expect(screen.getByRole('heading', { level: 2, name: '适用场景' })).toBeInTheDocument()
  })

  it('recovers from LLM preamble prefix ("好的, 以下是...")', () => {
    const polluted = `好的, 以下是您要的 SKILL.md 内容:

---
name: pr-review
description: short
allowed-tools: Bash
---

## 适用场景
review PRs`
    render(<SkillMdView content={polluted} />)
    const meta = screen.getByLabelText('skill metadata')
    expect(within(meta).getByText('pr-review')).toBeInTheDocument()
  })

  it('handles inline list triggers (single-line form)', () => {
    const inlineForm = `---
name: x
description: y
triggers: [foo, bar, baz]
allowed-tools: Bash
---

body
`
    render(<SkillMdView content={inlineForm} />)
    expect(screen.getByText('foo')).toBeInTheDocument()
    expect(screen.getByText('bar')).toBeInTheDocument()
    expect(screen.getByText('baz')).toBeInTheDocument()
  })
})
