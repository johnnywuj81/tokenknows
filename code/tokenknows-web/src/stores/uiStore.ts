/**
 * uiStore · 跨页 UI 状态 (sidebar / 通知抽屉 等)。不持久化。
 *
 * 设计依据: SharedFoundations.md §4.3
 */

import { create } from 'zustand'

interface UiState {
  sidebarOpen: boolean
  notificationOpen: boolean
  toggleSidebar: () => void
  setSidebar: (open: boolean) => void
  toggleNotification: () => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  notificationOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebar: (open) => set({ sidebarOpen: open }),
  toggleNotification: () => set((s) => ({ notificationOpen: !s.notificationOpen })),
}))
