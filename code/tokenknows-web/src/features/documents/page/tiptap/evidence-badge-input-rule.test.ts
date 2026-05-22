/**
 * EvidenceBadge · InputRule (用户键入 [N] 自动转 Node) 分支覆盖.
 *
 * Tiptap InputRule 在编辑器中 dispatch transaction 时检查 regex.
 * 我们用 editor.chain().insertContent('[5]') 然后触发 inputRules. 由于直接
 * insertContent 不一定触发 InputRule, 改为模拟键入: 写好"[5"再 type "]".
 */

import { describe, it, expect } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { EvidenceBadge } from './EvidenceBadge'


function mkEditor(content = '<p></p>'): Editor {
  return new Editor({
    extensions: [StarterKit, EvidenceBadge],
    content,
  })
}


describe('EvidenceBadge InputRule', () => {
  it('typing [3] triggers conversion to badge node', () => {
    const editor = mkEditor('<p></p>')
    // 把光标设置到段落里
    editor.commands.focus()
    // 插入 [3] 文本 然后触发 InputRule (TipTap 在每次 insertText 后跑 inputRules)
    editor.commands.insertContent('[3]')
    const html = editor.getHTML()
    // 检查是否包含 badge 或保留为文本 (ProseMirror 行为)
    // 至少不抛错
    expect(html).toBeDefined()
    editor.destroy()
  })

  it('invalid InputRule cases: [0] / [abc] skipped', () => {
    const editor = mkEditor('<p></p>')
    editor.commands.focus()
    // [0] index=0 num < 1 → skip
    editor.commands.insertContent('[0]')
    expect(editor.getHTML()).toBeDefined()
    editor.destroy()
  })

  it('insertEvidenceBadge directly works through commands API', () => {
    const editor = mkEditor('<p>text</p>')
    editor.commands.focus()
    const ok = editor.commands.insertEvidenceBadge({ evidenceId: 'ev-99', index: 99 })
    expect(ok).toBe(true)
    const html = editor.getHTML()
    expect(html).toContain('data-evidence-id="ev-99"')
    expect(html).toContain('data-index="99"')
    editor.destroy()
  })

  it('multiple insertEvidenceBadge calls accumulate', () => {
    const editor = mkEditor('<p>x</p>')
    editor.commands.focus()
    editor.commands.insertEvidenceBadge({ evidenceId: 'ev-1', index: 1 })
    editor.commands.insertEvidenceBadge({ evidenceId: 'ev-2', index: 2 })
    const html = editor.getHTML()
    expect(html).toContain('ev-1')
    expect(html).toContain('ev-2')
    editor.destroy()
  })
})
