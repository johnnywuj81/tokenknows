/**
 * SkillMdView · agent_skill 类型 chapter 的专属渲染器
 *
 * 为什么需要:
 *   通用 ChapterBlock 用 markdown-it 直接渲染整段 content. SKILL.md 开头的
 *   `---` YAML frontmatter 在 markdown-it 里会被识别为 `<hr>` (水平分隔线),
 *   `name: x` `description: y` 当成普通段落 — 渲染出来就是横线 + 一堆冒号文本,
 *   没法看. 本组件:
 *     1. 把 frontmatter 解析成结构化元数据卡 (chips / 文本)
 *     2. body 部分单独 markdown 渲染
 *
 * 注意: 当前是只读视图. 编辑 SKILL.md 需要重新生成 (内容字段重新蒸馏).
 *      未来可加 "编辑 metadata + 编辑 body" 的双面板交互.
 */

import { useMemo } from 'react'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// ── Frontmatter 解析 (hand-rolled · 不引 yaml 依赖) ─────────────

interface SkillFrontmatter {
  name?: string
  description?: string
  triggers: string[]
  allowedTools: string[]
  scope?: string
  category?: string
  /** 未识别的额外字段, 兜底显示 */
  extra: Record<string, string>
}

interface ParsedSkillMd {
  frontmatter: SkillFrontmatter
  body: string
  /** 解析报错 (没识别到 frontmatter / YAML 不合法等). 不为 null 时显示 raw. */
  parseError: string | null
}

function emptyFrontmatter(): SkillFrontmatter {
  return { triggers: [], allowedTools: [], extra: {} }
}

/**
 * LLM 输出污染清理 (镜像后端 _normalize_skill_md_text):
 *   - 剥首尾 ```fence
 *   - 前 20 行内找首个独占 `---` 行, 截掉 preamble
 */
function normalizeSkillMdText(raw: string): string {
  let s = raw.trim()
  if (s.startsWith('```')) {
    s = s.replace(/^```(?:[a-zA-Z][a-zA-Z0-9_+-]*)?\s*\n/, '')
    s = s.replace(/\n?```\s*$/, '')
    s = s.trim()
  }
  if (!s.startsWith('---\n') && !s.startsWith('---\r\n')) {
    const lines = s.split('\n')
    for (let i = 0; i < Math.min(lines.length, 20); i++) {
      if (lines[i].trim() === '---') {
        s = lines.slice(i).join('\n')
        break
      }
    }
  }
  return s
}

/**
 * 解析 SKILL.md 形如 `---\n<yaml>\n---\n<body>` 的结构.
 *
 * 简化版 YAML 解析 (够用): 仅支持
 *   - `key: value` (单行标量)
 *   - `key:` 后跟若干 `  - item` (列表)
 *
 * 不支持嵌套 map / 引号转义 (本场景用不到).
 *
 * 容错: 先剥 ```代码 fence + preamble (跟后端 _normalize_skill_md_text 一致),
 *      避免老 LLM 输出无视 prompt 约束时前端炸开.
 */
function parseSkillMd(text: string): ParsedSkillMd {
  const trimmed = normalizeSkillMdText(text)
  if (!trimmed.startsWith('---')) {
    return {
      frontmatter: emptyFrontmatter(),
      body: text,
      parseError: 'no frontmatter delimiter',
    }
  }
  // 找第二个 `---` 关闭分隔符
  const lines = trimmed.split('\n')
  let closeIdx = -1
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      closeIdx = i
      break
    }
  }
  if (closeIdx === -1) {
    return {
      frontmatter: emptyFrontmatter(),
      body: text,
      parseError: 'frontmatter close delimiter not found',
    }
  }

  const yamlLines = lines.slice(1, closeIdx)
  const body = lines.slice(closeIdx + 1).join('\n').trim()

  const fm = emptyFrontmatter()
  let currentListKey: string | null = null
  let currentListBuf: string[] | null = null

  const flushList = () => {
    if (currentListKey && currentListBuf) {
      if (currentListKey === 'triggers') {
        fm.triggers = currentListBuf
      } else {
        fm.extra[currentListKey] = currentListBuf.join(', ')
      }
    }
    currentListKey = null
    currentListBuf = null
  }

  for (const line of yamlLines) {
    if (line.trim() === '') continue
    // list item under previous key
    const listMatch = line.match(/^\s+-\s+(.+)$/)
    if (listMatch && currentListBuf) {
      currentListBuf.push(listMatch[1].trim())
      continue
    }
    // key: value 或 key:
    const kvMatch = line.match(/^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$/)
    if (!kvMatch) {
      flushList()
      continue
    }
    flushList()
    const key = kvMatch[1].toLowerCase()
    const rawValue = kvMatch[2].trim()
    if (rawValue === '') {
      // 列表开头
      currentListKey = key
      currentListBuf = []
      continue
    }
    switch (key) {
      case 'name':
        fm.name = rawValue
        break
      case 'description':
        fm.description = rawValue
        break
      case 'scope':
        fm.scope = rawValue
        break
      case 'category':
        fm.category = rawValue
        break
      case 'allowed-tools':
        fm.allowedTools = rawValue
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        break
      case 'triggers':
        // 同行 inline 列表也兼容: `triggers: [a, b, c]` 或 `triggers: a, b, c`
        fm.triggers = rawValue
          .replace(/^\[|\]$/g, '')
          .split(',')
          .map((s) => s.trim().replace(/^["']|["']$/g, ''))
          .filter(Boolean)
        break
      default:
        fm.extra[key] = rawValue
    }
  }
  flushList()

  return { frontmatter: fm, body, parseError: null }
}

// ── UI ────────────────────────────────────────────────────────

interface SkillMdViewProps {
  content: string
  /** 后端解析时记下来的错误 · 优先比前端 parseError 显示 (LLM 输出格式错) */
  backendParseError?: string | null
}

export function SkillMdView({ content, backendParseError }: SkillMdViewProps) {
  const parsed = useMemo(() => parseSkillMd(content), [content])
  const bodyHTML = useMemo(() => md.render(parsed.body), [parsed.body])
  const fm = parsed.frontmatter

  const error = backendParseError || parsed.parseError

  return (
    <div className="space-y-4">
      {error ? (
        <div
          className="rounded-md border border-danger-border bg-danger-bg/30 px-3 py-2 text-body-sm text-danger-dark"
          role="alert"
        >
          ⚠️ SKILL.md 格式异常: {error} · 已按 raw markdown 渲染.
        </div>
      ) : null}

      {/* 元数据卡 · 即使 frontmatter 不全也尽量显示 */}
      <section
        aria-label="skill metadata"
        className="space-y-2 rounded-md border border-border-subtle bg-bg-subtle/50 p-3"
      >
        {fm.name ? (
          <div className="flex items-baseline gap-2">
            <span className="font-ui text-caption text-text-muted">name</span>
            <code className="font-mono text-body-sm text-accent-primary">{fm.name}</code>
          </div>
        ) : null}

        {fm.description ? (
          <div className="flex items-baseline gap-2">
            <span className="font-ui text-caption text-text-muted">description</span>
            <p className="font-content text-body-sm text-text-primary">{fm.description}</p>
          </div>
        ) : null}

        {fm.triggers.length > 0 ? (
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-ui text-caption text-text-muted">triggers</span>
            <div className="flex flex-wrap gap-1">
              {fm.triggers.map((t) => (
                <span
                  key={t}
                  className="rounded-md border border-border-subtle bg-bg-card px-1.5 py-0.5 font-mono text-micro text-text-secondary"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {fm.allowedTools.length > 0 ? (
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-ui text-caption text-text-muted">allowed-tools</span>
            <div className="flex flex-wrap gap-1">
              {fm.allowedTools.map((tool) => {
                const isMcp = tool.startsWith('mcp__')
                return (
                  <span
                    key={tool}
                    className={
                      isMcp
                        ? 'rounded-md border border-accent-primary/40 bg-accent-primary-light px-1.5 py-0.5 font-mono text-micro text-accent-primary'
                        : 'rounded-md border border-success-border bg-success-bg px-1.5 py-0.5 font-mono text-micro text-success-dark'
                    }
                    title={isMcp ? 'MCP 工具' : '内置工具'}
                  >
                    {tool}
                  </span>
                )
              })}
            </div>
          </div>
        ) : null}

        {(fm.scope || fm.category) ? (
          <div className="flex flex-wrap items-baseline gap-3">
            {fm.scope ? (
              <span className="font-ui text-caption text-text-muted">
                scope · <code className="font-mono text-text-secondary">{fm.scope}</code>
              </span>
            ) : null}
            {fm.category ? (
              <span className="font-ui text-caption text-text-muted">
                category · <code className="font-mono text-text-secondary">{fm.category}</code>
              </span>
            ) : null}
          </div>
        ) : null}

        {/* 额外字段兜底 */}
        {Object.entries(fm.extra).length > 0 ? (
          <details className="text-caption text-text-muted">
            <summary className="cursor-pointer font-ui">其它字段 ({Object.keys(fm.extra).length})</summary>
            <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
              {Object.entries(fm.extra).map(([k, v]) => (
                <span key={k} className="contents">
                  <dt className="font-mono">{k}</dt>
                  <dd className="font-mono break-all">{v}</dd>
                </span>
              ))}
            </dl>
          </details>
        ) : null}
      </section>

      {/* body · 普通 markdown 渲染 */}
      <div
        className="prose-skill font-content text-body text-text-primary"
        dangerouslySetInnerHTML={{ __html: bodyHTML }}
      />
    </div>
  )
}
