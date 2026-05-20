/**
 * documentUiStore · T04 / T06 / T07 / T08 共享的 UI 状态。不持久化。
 *
 * 设计依据: SharedFoundations.md §4.4
 *
 * 注意: activeEvidenceId / activeEventId 与 URL query string 双向同步,
 *       由各 drawer 组件 useEffect 监听 URL 变化。
 */

import { create } from 'zustand'

interface DocumentUiState {
  // T07 证据抽屉
  evidenceOpen: boolean
  activeEvidenceId: string | null

  // T04 事件抽屉
  eventDrawerOpen: boolean
  activeEventId: string | null

  // T08 重生成对话框
  regenerateOpen: boolean
  regenerateChapterId: string | null

  // actions
  openEvidence: (id: string) => void
  closeEvidence: () => void
  openEventDrawer: (id: string) => void
  closeEventDrawer: () => void
  openRegenerate: (chapterId: string) => void
  closeRegenerate: () => void
}

export const useDocumentUiStore = create<DocumentUiState>((set) => ({
  evidenceOpen: false,
  activeEvidenceId: null,
  eventDrawerOpen: false,
  activeEventId: null,
  regenerateOpen: false,
  regenerateChapterId: null,

  openEvidence: (id) => set({ evidenceOpen: true, activeEvidenceId: id }),
  closeEvidence: () => set({ evidenceOpen: false, activeEvidenceId: null }),
  openEventDrawer: (id) => set({ eventDrawerOpen: true, activeEventId: id }),
  closeEventDrawer: () => set({ eventDrawerOpen: false, activeEventId: null }),
  openRegenerate: (chapterId) => set({ regenerateOpen: true, regenerateChapterId: chapterId }),
  closeRegenerate: () => set({ regenerateOpen: false, regenerateChapterId: null }),
}))
