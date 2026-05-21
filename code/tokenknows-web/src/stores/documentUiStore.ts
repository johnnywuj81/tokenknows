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
  // T07 证据抽屉 (重设计 - chapterId 是数据 key, evidenceId 是高亮项)
  evidenceOpen: boolean
  /** 抽屉关联的 chapter (决定 fetch 哪份证据列表). */
  evidenceChapterId: string | null
  /** 当前高亮的 evidence (切换不重 fetch). */
  activeEvidenceId: string | null

  // T04 事件抽屉
  eventDrawerOpen: boolean
  activeEventId: string | null

  // T08 重生成对话框
  regenerateOpen: boolean
  regenerateChapterId: string | null

  // T11 发布对话框
  publishOpen: boolean

  // actions
  /** 打开抽屉: 必须传 chapterId, evidenceId 可选 (默认聚焦第 1 条). */
  openEvidence: (chapterId: string, evidenceId?: string | null) => void
  setActiveEvidence: (evidenceId: string | null) => void
  closeEvidence: () => void
  openEventDrawer: (id: string) => void
  closeEventDrawer: () => void
  openRegenerate: (chapterId: string) => void
  closeRegenerate: () => void
  openPublish: () => void
  closePublish: () => void
}

export const useDocumentUiStore = create<DocumentUiState>((set) => ({
  evidenceOpen: false,
  evidenceChapterId: null,
  activeEvidenceId: null,
  eventDrawerOpen: false,
  activeEventId: null,
  regenerateOpen: false,
  regenerateChapterId: null,
  publishOpen: false,

  openEvidence: (chapterId, evidenceId = null) =>
    set({ evidenceOpen: true, evidenceChapterId: chapterId, activeEvidenceId: evidenceId }),
  setActiveEvidence: (evidenceId) => set({ activeEvidenceId: evidenceId }),
  closeEvidence: () =>
    set({ evidenceOpen: false, evidenceChapterId: null, activeEvidenceId: null }),
  openEventDrawer: (id) => set({ eventDrawerOpen: true, activeEventId: id }),
  closeEventDrawer: () => set({ eventDrawerOpen: false, activeEventId: null }),
  openRegenerate: (chapterId) => set({ regenerateOpen: true, regenerateChapterId: chapterId }),
  closeRegenerate: () => set({ regenerateOpen: false, regenerateChapterId: null }),
  openPublish: () => set({ publishOpen: true }),
  closePublish: () => set({ publishOpen: false }),
}))
