/**
 * EvidenceBadge TipTap Node · 通过编辑器集成测.
 *
 * 测试策略: 在 jsdom 中创建临时 TipTap editor, 验证 parseHTML / renderHTML /
 * commands.insertEvidenceBadge 工作正常.
 */

import { describe, it, expect } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { EvidenceBadge } from './EvidenceBadge'


function mkEditor(content: string): Editor {
  return new Editor({
    extensions: [StarterKit, EvidenceBadge],
    content,
  })
}


describe('EvidenceBadge node', () => {
  it('parses <span class="evidence-badge"> to Node', () => {
    const editor = mkEditor(
      '<p>before <span class="evidence-badge" data-evidence-id="ev1" data-index="3">3</span> after</p>',
    )
    const html = editor.getHTML()
    expect(html).toContain('evidence-badge')
    expect(html).toContain('data-evidence-id="ev1"')
    expect(html).toContain('data-index="3"')
    editor.destroy()
  })

  it('round-trips: parse → render preserves attrs', () => {
    const editor = mkEditor(
      '<p>x <span class="evidence-badge" data-evidence-id="ev-x" data-index="5">5</span></p>',
    )
    const html = editor.getHTML()
    expect(html).toMatch(/data-evidence-id="ev-x"/)
    expect(html).toMatch(/data-index="5"/)
    editor.destroy()
  })

  it('parseHTML index fallback from textContent when no data-index', () => {
    const editor = mkEditor(
      '<p><span class="evidence-badge" data-evidence-id="ev1">7</span></p>',
    )
    const html = editor.getHTML()
    expect(html).toMatch(/data-index="7"/)
    editor.destroy()
  })

  it('parseHTML index falls back to 1 when textContent non-numeric', () => {
    const editor = mkEditor(
      '<p><span class="evidence-badge" data-evidence-id="ev1">xxx</span></p>',
    )
    const html = editor.getHTML()
    expect(html).toMatch(/data-index="1"/)
    editor.destroy()
  })

  it('insertEvidenceBadge command inserts node', () => {
    const editor = mkEditor('<p>hello</p>')
    editor.commands.insertEvidenceBadge({ evidenceId: 'ev-new', index: 42 })
    const html = editor.getHTML()
    expect(html).toContain('data-evidence-id="ev-new"')
    expect(html).toContain('data-index="42"')
    editor.destroy()
  })

  it('renderHTML output uses contenteditable=false', () => {
    const editor = mkEditor('<p>x</p>')
    editor.commands.insertEvidenceBadge({ evidenceId: 'ev1', index: 1 })
    expect(editor.getHTML()).toMatch(/contenteditable="false"/)
    editor.destroy()
  })

  it('null evidenceId omits data-evidence-id attribute', () => {
    const editor = mkEditor('<p>x</p>')
    editor.commands.insertEvidenceBadge({ evidenceId: null as unknown as string, index: 3 })
    const html = editor.getHTML()
    expect(html).not.toMatch(/data-evidence-id="null"/)
    editor.destroy()
  })

  it('node is atomic + inline (cannot split)', () => {
    const editor = mkEditor('<p><span class="evidence-badge" data-evidence-id="ev1" data-index="1">1</span></p>')
    // 进入文档: cursor 在 evidence 前/后, 中间不可
    const schema = editor.schema
    const nodeType = schema.nodes.evidenceBadge
    expect(nodeType.spec.inline).toBe(true)
    expect(nodeType.spec.atom).toBe(true)
    editor.destroy()
  })

  it('alternative tag evidence-badge also parses', () => {
    const editor = mkEditor(
      '<p><evidence-badge data-evidence-id="ev-alt" data-index="9">9</evidence-badge></p>',
    )
    const html = editor.getHTML()
    expect(html).toContain('evidence-badge')
    editor.destroy()
  })
})
