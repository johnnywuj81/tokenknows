/**
 * RegenerateDialog · T08 章节重生成对话框 · 真 LLM 调用
 *
 * 流程:
 *   1. 用户点章节 footer "重生成" → 打开 dialog (chapterId 已写入 store)
 *   2. 用户填指令 (必填) + 可选 model override
 *   3. 提交 → useRegenerate mutation 同步等 LLM 完成
 *   4. mutation isPending 期间: DocumentPage 会把 ChapterBlock regenerating=true
 *      让编辑禁用 + 显示锁态
 *   5. 成功: 关闭 dialog + invalidate queries 让 ChapterBlock 拉新内容
 *   6. 失败: 显示错误, dialog 不关
 */

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { RefreshCcw, Loader2, AlertCircle } from 'lucide-react'
import { useDocumentUiStore } from '@/stores/documentUiStore'
import { useRegenerate } from '../../hooks/useRegenerate'
import { useChapters } from '../../hooks/useChapters'
import { getErrorMessage } from '@/lib/api'

interface RegenerateDialogProps {
  assetId: string | null | undefined
}

interface ModelChoice {
  label: string
  provider?: string
  model?: string
}

// MVP 提供的模型档位 - 真 LLM 路径都走 Ollama (China 网络限制).
const MODEL_CHOICES: ModelChoice[] = [
  { label: '默认 · 跟随任务配置 (Ollama · minimax-m2:cloud)' },
  { label: 'Ollama · gpt-oss:20b (本地, 离线可用)', provider: 'ollama', model: 'gpt-oss:20b' },
  {
    label: 'Ollama · minimax-m2:cloud (云端 230B 推理)',
    provider: 'ollama',
    model: 'minimax-m2:cloud',
  },
]

export function RegenerateDialog({ assetId }: RegenerateDialogProps) {
  const open = useDocumentUiStore((s) => s.regenerateOpen)
  const chapterId = useDocumentUiStore((s) => s.regenerateChapterId)
  const close = useDocumentUiStore((s) => s.closeRegenerate)

  const chapters = useChapters(assetId ?? undefined).data ?? []
  const chapter = chapters.find((c) => c.id === chapterId) ?? null

  const [instruction, setInstruction] = useState('')
  const [modelChoiceIdx, setModelChoiceIdx] = useState(0)
  const mutation = useRegenerate()

  const trimmed = instruction.trim()
  const canSubmit =
    Boolean(assetId && chapterId) && trimmed.length >= 5 && !mutation.isPending

  function handleOpenChange(o: boolean) {
    if (!o && !mutation.isPending) {
      // 关闭时清状态
      setInstruction('')
      setModelChoiceIdx(0)
      mutation.reset()
      close()
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!assetId || !chapterId || !canSubmit) return
    const choice = MODEL_CHOICES[modelChoiceIdx]
    try {
      await mutation.mutateAsync({
        assetId,
        chapterId,
        instruction: trimmed,
        provider: choice.provider,
        model: choice.model,
      })
      // 成功 → 关闭并清状态
      setInstruction('')
      setModelChoiceIdx(0)
      mutation.reset()
      close()
    } catch {
      // 失败 - mutation.error 已经包含错误信息, 通过 UI 显示
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-content">
              <RefreshCcw className="size-4" />
              重生成章节
            </DialogTitle>
            <DialogDescription className="font-ui text-caption text-text-muted">
              本章节内容会被 LLM 按你的指令完整重写, 自动保存历史到 regeneration_history.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* 目标章节 */}
            <div className="rounded-md border border-border-subtle bg-bg-warm/40 px-3 py-2">
              <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
                目标章节
              </p>
              <p className="mt-0.5 font-content text-body text-text-primary">
                {chapter ? `§${chapter.order_index + 1} ${chapter.title}` : '—'}
              </p>
            </div>

            {/* 指令 textarea */}
            <div>
              <label
                htmlFor="regen-instruction"
                className="font-ui text-caption font-medium text-text-secondary"
              >
                重生成指令
                <span className="ml-1 text-danger">*</span>
              </label>
              <textarea
                id="regen-instruction"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={mutation.isPending}
                placeholder="例: 用更简洁的语气重写, 强调本周完成的 PR 和关键决策, 不超过 200 字"
                rows={4}
                className="mt-1.5 w-full resize-none rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary placeholder:text-text-subtle focus:border-accent-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                required
                minLength={5}
              />
              <p className="mt-1 font-ui text-micro text-text-subtle">
                至少 5 个字符. 当前 {trimmed.length} 字符.
              </p>
            </div>

            {/* 模型选择 */}
            <div>
              <label
                htmlFor="regen-model"
                className="font-ui text-caption font-medium text-text-secondary"
              >
                模型
              </label>
              <select
                id="regen-model"
                value={modelChoiceIdx}
                onChange={(e) => setModelChoiceIdx(Number(e.target.value))}
                disabled={mutation.isPending}
                className="mt-1.5 w-full rounded-md border border-border-subtle bg-bg-card px-3 py-2 font-ui text-body-sm text-text-primary focus:border-accent-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                {MODEL_CHOICES.map((c, i) => (
                  <option key={i} value={i}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 错误 */}
            {mutation.error ? (
              <div className="flex items-start gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-danger">
                <AlertCircle className="size-4 mt-0.5 shrink-0" />
                <p className="font-ui text-body-sm">
                  {getErrorMessage(mutation.error)}
                </p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleOpenChange(false)}
              disabled={mutation.isPending}
              className="font-ui"
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={!canSubmit}
              className="font-ui"
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  重生成中…
                </>
              ) : (
                <>
                  <RefreshCcw className="size-3.5" />
                  提交重生成
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
