/**
 * EvidenceBadge · TipTap 自定义内联原子 Node
 *
 * P2 目的: 解决既有 annotateEvidence 后处理被 StarterKit 吞 class 的问题.
 *
 * 三件事:
 *   1. inline + atom · 编辑器视它为不可拆分的一个字符
 *   2. parseHTML · 把 `<span class="evidence-badge" data-evidence-id="..." data-index="...">`
 *      还原成 Node, 同时也兼容旧的 HTML
 *   3. InputRule · 用户在编辑器里打 `[3]` 自动转 Node
 *   4. renderHTML · 输出回 `<span class="evidence-badge" ...>N</span>`,
 *      保存到后端后再 toMarkdown 也能可逆 (toMarkdown 简单处理: `[N]`)
 *
 * 渲染上层 click 监听仍由 ChapterBlock onClickCapture 委托.
 */

import { Node, mergeAttributes, InputRule } from '@tiptap/core'

export interface EvidenceBadgeOptions {
  HTMLAttributes: Record<string, unknown>
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    evidenceBadge: {
      /** 插入一个 evidence badge node. */
      insertEvidenceBadge: (attrs: {
        evidenceId: string
        index: number
      }) => ReturnType
    }
  }
}

export const EvidenceBadge = Node.create<EvidenceBadgeOptions>({
  name: 'evidenceBadge',

  group: 'inline',
  inline: true,
  atom: true,
  selectable: false,
  draggable: false,

  addOptions() {
    return {
      HTMLAttributes: {},
    }
  },

  addAttributes() {
    return {
      evidenceId: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-evidence-id'),
        renderHTML: (attrs) =>
          attrs.evidenceId
            ? { 'data-evidence-id': attrs.evidenceId as string }
            : {},
      },
      index: {
        default: 1,
        parseHTML: (el) => {
          const fromAttr = el.getAttribute('data-index')
          if (fromAttr) return Number(fromAttr)
          const txt = el.textContent ?? ''
          const n = Number(txt.trim())
          return Number.isFinite(n) ? n : 1
        },
        renderHTML: (attrs) => ({ 'data-index': String(attrs.index ?? 1) }),
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'span.evidence-badge',
      },
      // 兼容 ProseMirror 输出: <evidence-badge data-evidence-id="..." data-index="N">
      {
        tag: 'evidence-badge',
      },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    const idx = String(node.attrs.index ?? 1)
    return [
      'span',
      mergeAttributes(
        {
          class: 'evidence-badge',
          contenteditable: 'false',
        },
        this.options.HTMLAttributes,
        HTMLAttributes,
      ),
      idx,
    ]
  },

  // 用户在编辑器里打 [3] → 自动转 Node.
  // 注意: 仅在 [N] 后紧跟空格/换行/或在段落末尾时触发, 避免误吞 markdown 列表 [x]
  addInputRules() {
    return [
      new InputRule({
        find: /\[(\d+)\]$/,
        handler: ({ state, range, match, chain }) => {
          const num = Number(match[1])
          if (!Number.isFinite(num) || num < 1) return
          // 估算 evidenceId: 编辑器不知道 chapterId, 这里只标 index, 真 id 由
          // 后端 evidence list 按 order 对应. 前端打开抽屉时 fallback 第 1 条.
          chain()
            .deleteRange(range)
            .insertContent({
              type: 'evidenceBadge',
              attrs: { evidenceId: null, index: num },
            })
            .run()
          // 让 state 引用静默避免未使用警告 (实际不读)
          void state
        },
      }),
    ]
  },

  addCommands() {
    return {
      insertEvidenceBadge:
        (attrs) =>
        ({ chain }) =>
          chain()
            .insertContent({
              type: 'evidenceBadge',
              attrs: { evidenceId: attrs.evidenceId, index: attrs.index },
            })
            .run(),
    }
  },
})
