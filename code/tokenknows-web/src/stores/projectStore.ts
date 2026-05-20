/**
 * projectStore · 当前选中项目 ID (持久化)。
 *
 * 设计依据: SharedFoundations.md §4.2
 * Key: tokenknows_current_project
 *
 * 切换项目时由调用方负责 invalidate 该项目相关的 query。
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ProjectState {
  currentProjectId: string | null
  setCurrent: (id: string | null) => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      currentProjectId: null,
      setCurrent: (id) => set({ currentProjectId: id }),
    }),
    { name: 'tokenknows_current_project' },
  ),
)
