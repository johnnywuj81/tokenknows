/**
 * useChapterAutosave · TipTap 自动保存状态机
 *
 * 设计依据 TaskTechDesign T06 关键决策:
 *   - debounce 2s + 字段级 diff 提交
 *   - TipTap onUpdate 每按键触发, 必须 debounce
 *   - 保存失败 → localStorage 兜底 + state=error
 *   - 乐观更新关闭, 以服务端为准 reconcile (服务端可能 reformat)
 *   - 与"重生成"互斥 (调用方负责传 regenerating=true 时不触发 handleEdit)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, isApiError } from '@/lib/api'
import type { Chapter } from '@/types/api'

export type AutosaveState = 'idle' | 'editing' | 'saving' | 'saved' | 'error'

interface UseChapterAutosaveResult {
  state: AutosaveState
  /** 服务端最近一次确认的内容 (用于 reconcile 外部刷新). */
  savedContent: string
  /** 编辑器 onUpdate 调用此函数 (内部 debounce). */
  handleEdit: (newContent: string) => void
  /** 错误信息 (state='error' 时显示). */
  error: string | null
}

export function useChapterAutosave(chapter: Chapter): UseChapterAutosaveResult {
  const [savedContent, setSavedContent] = useState<string>(chapter.content)
  const [state, setState] = useState<AutosaveState>('idle')
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const idleRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const queryClient = useQueryClient()

  // 不做 prop → state 同步.
  // 调用方对 ChapterBlock 用 key={chapter.id} 让外部变化时整体 remount
  // (避开 React 19 react-hooks/set-state-in-effect 严禁规则).

  // 清理 timers
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      if (idleRef.current) clearTimeout(idleRef.current)
    },
    [],
  )

  const performSave = useCallback(
    async (newContent: string) => {
      setState('saving')
      setError(null)
      try {
        const { data } = await api.patch<Chapter>(
          `/assets/${chapter.asset_id}/chapters/${chapter.id}`,
          { content: newContent },
        )
        setSavedContent(data.content)
        setState('saved')
        // 同步 cache (其它使用 chapters query 的组件能看到新内容)
        queryClient.setQueryData(
          ['assets', chapter.asset_id, 'chapters'],
          (old: Chapter[] | undefined) =>
            old ? old.map((c) => (c.id === chapter.id ? data : c)) : old,
        )
        // 1.5s 后回到 idle
        if (idleRef.current) clearTimeout(idleRef.current)
        idleRef.current = setTimeout(() => setState('idle'), 1500)
        // 清掉 localStorage 兜底
        try {
          localStorage.removeItem(`tokenknows_draft_${chapter.id}`)
        } catch {
          /* SSR-safe noop */
        }
      } catch (err: unknown) {
        const msg = isApiError(err) ? err.message : '保存失败'
        setState('error')
        setError(msg)
        // 失败兜底 - 草稿留 localStorage 不丢
        try {
          localStorage.setItem(`tokenknows_draft_${chapter.id}`, newContent)
        } catch {
          /* SSR-safe noop */
        }
      }
    },
    [chapter.asset_id, chapter.id, queryClient],
  )

  const handleEdit = useCallback(
    (newContent: string) => {
      if (newContent === savedContent) return
      setState('editing')
      setError(null)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => performSave(newContent), 2000)
    },
    [savedContent, performSave],
  )

  return { state, savedContent, handleEdit, error }
}
