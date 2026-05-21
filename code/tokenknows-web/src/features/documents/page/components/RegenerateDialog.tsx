/**
 * RegenerateDialog · T06 Phase 3 stub (T08 完整实现).
 *
 * 章节 footer "重生成" → 这里展示 placeholder.
 * T08 任务包会接 POST /assets/:id/chapters/:chapter_id/regenerate + 模型选择 + instruction.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { RefreshCcw, Construction } from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'

export function RegenerateDialog() {
  const open = useDocumentUiStore((s) => s.regenerateOpen)
  const chapterId = useDocumentUiStore((s) => s.regenerateChapterId)
  const close = useDocumentUiStore((s) => s.closeRegenerate)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-content">
            <RefreshCcw className="size-4" />
            重生成章节 (T08 占位)
          </DialogTitle>
          <DialogDescription>
            目标章节: <code className="font-mono">{chapterId ?? '—'}</code>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg p-3 text-warning">
            <Construction className="size-4 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p className="font-ui text-body-sm font-medium">T08 完整版会包含:</p>
              <ul className="font-ui text-caption">
                <li>· 模型选择 (Claude / GPT / Ollama, 含 dry-run preview)</li>
                <li>· 重生成 instruction 输入 (自然语言要求)</li>
                <li>· 候选 ValueSegment 预览 (本次会引用哪些事件)</li>
                <li>· "本章 readOnly 期间, 编辑会被禁用"</li>
              </ul>
            </div>
          </div>

          <p className="text-caption text-text-muted">
            提交后会 POST /assets/.../regenerate, 章节状态变 regenerating,
            ChapterBlock editable=false + 灰化 + spinner. 完成后内容替换为 LLM 新版本.
          </p>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={close} className="font-ui">
            关闭
          </Button>
          <Button disabled className="font-ui">
            提交重生成 (T08)
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
