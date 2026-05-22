/**
 * BottomActionBar · T09 底部固定操作栏
 *
 * 三个操作:
 *   1. "全部通过 + 进入发布" - 仅当所有章节 approved 时可点; 占位 T11 发布入口
 *   2. "退回修改" - asset 整体退回给 Editor 继续修改 (任一章节已退回时高亮)
 *      (LLM 不背责任; 真正"重写"的人是 Editor, 或 Editor 触发的 regenerate_chapter)
 *   3. "保存进度" - 不做服务端写, 仅作 UX 提示 (当前 mutation 都是即时落库)
 */

import { useNavigate } from 'react-router-dom'
import { Send, RotateCcw, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Asset, Chapter } from '@/types/api'

interface BottomActionBarProps {
  asset: Asset
  chapters: Chapter[]
  projectId: string | undefined
  onAllApproved: () => void
}

export function BottomActionBar({
  asset,
  chapters,
  projectId,
  onAllApproved,
}: BottomActionBarProps) {
  const navigate = useNavigate()
  const approvedCount = chapters.filter((c) => c.approval_state === 'approved').length
  const rejectedCount = chapters.filter((c) => c.approval_state === 'rejected').length
  const allApproved = chapters.length > 0 && approvedCount === chapters.length
  const hasRejected = rejectedCount > 0

  return (
    <footer
      className="flex items-center justify-between gap-3 border-t border-border-subtle bg-bg-card px-6 py-3"
      aria-label="审批操作"
    >
      <div className="font-ui text-caption text-text-muted">
        审批进度: {approvedCount} 通过 · {rejectedCount} 退回 · {chapters.length - approvedCount - rejectedCount} 待审
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            // 即时落库, 无需保存. 提供 UX 反馈即可.
            // (将来可加 toast)
          }}
          className="font-ui text-caption"
          title="所有章节状态都是即时入库, 无需手动保存"
        >
          <Save className="size-3.5" />
          保存进度
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!hasRejected}
          onClick={() => {
            if (projectId) {
              navigate(`/projects/${projectId}/documents/${asset.id}`)
            }
          }}
          className="font-ui text-caption"
        >
          <RotateCcw className="size-3.5" />
          退回修改
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!allApproved}
          onClick={onAllApproved}
          className="font-ui text-caption"
        >
          <Send className="size-3.5" />
          全部通过 · 进入发布 (T11)
        </Button>
      </div>
    </footer>
  )
}
