/**
 * 4 个 Zustand store 单测 · 状态变更 + persist 隔离.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'
import { useProjectStore } from './projectStore'
import { useUiStore } from './uiStore'
import { useDocumentUiStore } from './documentUiStore'
import type { User } from '@/types/api'

const mockUser: User = {
  id: 'u1',
  email: 'demo@x.com',
  display_name: 'Demo',
  is_instance_admin: false,
  email_verified_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  // 重置 localStorage 隔离 persist
  localStorage.clear()
  useAuthStore.getState().logout()
  useProjectStore.getState().setCurrent(null)
  useUiStore.setState({ sidebarOpen: true, notificationOpen: false })
  useDocumentUiStore.setState({
    evidenceOpen: false, evidenceChapterId: null, activeEvidenceId: null,
    eventDrawerOpen: false, activeEventId: null,
    regenerateOpen: false, regenerateChapterId: null,
    publishOpen: false,
  })
})


describe('authStore', () => {
  it('initial state', () => {
    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  })

  it('setAuth flips state', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok-1')
    const s = useAuthStore.getState()
    expect(s.user).toEqual(mockUser)
    expect(s.accessToken).toBe('tok-1')
    expect(s.isAuthenticated).toBe(true)
  })

  it('setUser updates user but keeps token', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok-1')
    useAuthStore.getState().setUser({ ...mockUser, display_name: 'Renamed' })
    const s = useAuthStore.getState()
    expect(s.user?.display_name).toBe('Renamed')
    expect(s.accessToken).toBe('tok-1')
  })

  it('logout clears all', () => {
    useAuthStore.getState().setAuth(mockUser, 'tok-1')
    useAuthStore.getState().logout()
    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  })
})


describe('projectStore', () => {
  it('initial state null', () => {
    expect(useProjectStore.getState().currentProjectId).toBeNull()
  })

  it('setCurrent updates id', () => {
    useProjectStore.getState().setCurrent('proj-1')
    expect(useProjectStore.getState().currentProjectId).toBe('proj-1')
  })

  it('setCurrent null clears', () => {
    useProjectStore.getState().setCurrent('proj-1')
    useProjectStore.getState().setCurrent(null)
    expect(useProjectStore.getState().currentProjectId).toBeNull()
  })
})


describe('uiStore', () => {
  it('sidebarOpen defaults true', () => {
    expect(useUiStore.getState().sidebarOpen).toBe(true)
  })

  it('toggleSidebar flips', () => {
    useUiStore.getState().toggleSidebar()
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    useUiStore.getState().toggleSidebar()
    expect(useUiStore.getState().sidebarOpen).toBe(true)
  })

  it('setSidebar explicit', () => {
    useUiStore.getState().setSidebar(false)
    expect(useUiStore.getState().sidebarOpen).toBe(false)
  })

  it('toggleNotification flips', () => {
    useUiStore.getState().toggleNotification()
    expect(useUiStore.getState().notificationOpen).toBe(true)
  })
})


describe('documentUiStore', () => {
  it('openEvidence sets chapter + active', () => {
    useDocumentUiStore.getState().openEvidence('ch-1', 'ev-1')
    const s = useDocumentUiStore.getState()
    expect(s.evidenceOpen).toBe(true)
    expect(s.evidenceChapterId).toBe('ch-1')
    expect(s.activeEvidenceId).toBe('ev-1')
  })

  it('openEvidence without evidenceId defaults null', () => {
    useDocumentUiStore.getState().openEvidence('ch-1')
    expect(useDocumentUiStore.getState().activeEvidenceId).toBeNull()
  })

  it('setActiveEvidence switches highlight', () => {
    useDocumentUiStore.getState().openEvidence('ch-1', 'ev-1')
    useDocumentUiStore.getState().setActiveEvidence('ev-2')
    const s = useDocumentUiStore.getState()
    expect(s.activeEvidenceId).toBe('ev-2')
    expect(s.evidenceChapterId).toBe('ch-1')   // chapter 不变
  })

  it('closeEvidence resets all', () => {
    useDocumentUiStore.getState().openEvidence('ch-1', 'ev-1')
    useDocumentUiStore.getState().closeEvidence()
    const s = useDocumentUiStore.getState()
    expect(s.evidenceOpen).toBe(false)
    expect(s.evidenceChapterId).toBeNull()
    expect(s.activeEvidenceId).toBeNull()
  })

  it('openEventDrawer / closeEventDrawer', () => {
    useDocumentUiStore.getState().openEventDrawer('ev-x')
    expect(useDocumentUiStore.getState().eventDrawerOpen).toBe(true)
    expect(useDocumentUiStore.getState().activeEventId).toBe('ev-x')
    useDocumentUiStore.getState().closeEventDrawer()
    expect(useDocumentUiStore.getState().eventDrawerOpen).toBe(false)
    expect(useDocumentUiStore.getState().activeEventId).toBeNull()
  })

  it('openRegenerate / closeRegenerate', () => {
    useDocumentUiStore.getState().openRegenerate('ch-1')
    expect(useDocumentUiStore.getState().regenerateOpen).toBe(true)
    useDocumentUiStore.getState().closeRegenerate()
    expect(useDocumentUiStore.getState().regenerateOpen).toBe(false)
    expect(useDocumentUiStore.getState().regenerateChapterId).toBeNull()
  })

  it('openPublish / closePublish', () => {
    useDocumentUiStore.getState().openPublish()
    expect(useDocumentUiStore.getState().publishOpen).toBe(true)
    useDocumentUiStore.getState().closePublish()
    expect(useDocumentUiStore.getState().publishOpen).toBe(false)
  })
})
