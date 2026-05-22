/**
 * Project wizard reducer · 纯函数, 高 ROI 测试.
 */

import { describe, it, expect } from 'vitest'
import {
  initialState,
  wizardReducer,
  canAdvance,
  STEP_TITLES,
  type WizardState,
} from './wizard'
import type { Datasource, Project } from '@/types/api'


const mockProject: Project = {
  id: 'p1',
  name: 'demo',
  description: '',
  owner_id: 'u1',
  llm_egress_enabled: false,
  task_egress_config: {},
  custom_redaction_terms: [],
  brand_theme: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const mockDatasource: Datasource = {
  id: 'd1',
  project_id: 'p1',
  type: 'github',
  name: 'demo repo',
  config: {},
  health: 'healthy',
  last_synced_at: null,
  created_at: new Date().toISOString(),
}


describe('wizardReducer', () => {
  describe('SET_NAME', () => {
    it('sets name and clears nameError', () => {
      const s: WizardState = { ...initialState, nameError: '旧错误' }
      const next = wizardReducer(s, { type: 'SET_NAME', value: 'demo' })
      expect(next.name).toBe('demo')
      expect(next.nameError).toBe(null)
    })
  })

  describe('SET_DESCRIPTION', () => {
    it('sets description', () => {
      const next = wizardReducer(initialState, {
        type: 'SET_DESCRIPTION',
        value: '描述',
      })
      expect(next.description).toBe('描述')
    })
  })

  describe('TOGGLE_DATASOURCE', () => {
    it('adds when absent', () => {
      const next = wizardReducer(initialState, {
        type: 'TOGGLE_DATASOURCE',
        ds: 'github',
      })
      expect(next.selectedTypes).toEqual(['github'])
    })

    it('removes when present', () => {
      const s: WizardState = { ...initialState, selectedTypes: ['github', 'slack'] }
      const next = wizardReducer(s, { type: 'TOGGLE_DATASOURCE', ds: 'github' })
      expect(next.selectedTypes).toEqual(['slack'])
    })

    it('two toggles → empty', () => {
      let s = initialState
      s = wizardReducer(s, { type: 'TOGGLE_DATASOURCE', ds: 'github' })
      s = wizardReducer(s, { type: 'TOGGLE_DATASOURCE', ds: 'github' })
      expect(s.selectedTypes).toEqual([])
    })
  })

  describe('NAME_CONFLICT', () => {
    it('sets nameError and step back to 1', () => {
      const s: WizardState = { ...initialState, step: 2 }
      const next = wizardReducer(s, {
        type: 'NAME_CONFLICT',
        message: '项目名已存在',
      })
      expect(next.nameError).toBe('项目名已存在')
      expect(next.step).toBe(1)
    })
  })

  describe('CLEAR_NAME_ERROR', () => {
    it('clears nameError', () => {
      const s: WizardState = { ...initialState, nameError: '错误' }
      const next = wizardReducer(s, { type: 'CLEAR_NAME_ERROR' })
      expect(next.nameError).toBe(null)
    })
  })

  describe('PROJECT_CREATED', () => {
    it('stores created project', () => {
      const next = wizardReducer(initialState, {
        type: 'PROJECT_CREATED',
        project: mockProject,
      })
      expect(next.createdProject).toBe(mockProject)
    })
  })

  describe('DATASOURCE_ADDED', () => {
    it('appends to addedDatasources', () => {
      const next = wizardReducer(initialState, {
        type: 'DATASOURCE_ADDED',
        ds: mockDatasource,
      })
      expect(next.addedDatasources).toEqual([mockDatasource])
    })

    it('does not mutate prior array', () => {
      const s: WizardState = { ...initialState, addedDatasources: [mockDatasource] }
      const next = wizardReducer(s, {
        type: 'DATASOURCE_ADDED',
        ds: { ...mockDatasource, id: 'd2' },
      })
      expect(next.addedDatasources.length).toBe(2)
      expect(s.addedDatasources.length).toBe(1) // 原 state 不变
    })
  })

  describe('GO_NEXT', () => {
    it('step++ but clamps at 4', () => {
      let s = wizardReducer(initialState, { type: 'GO_NEXT' })
      expect(s.step).toBe(2)
      s = wizardReducer(s, { type: 'GO_NEXT' })
      expect(s.step).toBe(3)
      s = wizardReducer(s, { type: 'GO_NEXT' })
      expect(s.step).toBe(4)
      s = wizardReducer(s, { type: 'GO_NEXT' })
      expect(s.step).toBe(4) // clamp
    })
  })

  describe('GO_PREV', () => {
    it('step-- but clamps at 1', () => {
      const s: WizardState = { ...initialState, step: 3 }
      const a = wizardReducer(s, { type: 'GO_PREV' })
      expect(a.step).toBe(2)
      const b = wizardReducer(initialState, { type: 'GO_PREV' })
      expect(b.step).toBe(1) // clamp
    })
  })

  describe('GO_TO', () => {
    it('jumps to specific step', () => {
      const next = wizardReducer(initialState, { type: 'GO_TO', step: 3 })
      expect(next.step).toBe(3)
    })
  })

  describe('unknown action', () => {
    it('returns state unchanged (default branch)', () => {
      // @ts-expect-error - 故意传 unknown type 触发 default
      const next = wizardReducer(initialState, { type: 'UNKNOWN' })
      expect(next).toBe(initialState)
    })
  })
})


describe('canAdvance', () => {
  it('step 1: false when name < 2 chars', () => {
    expect(canAdvance({ ...initialState, name: 'a' })).toBe(false)
  })

  it('step 1: false when whitespace only', () => {
    expect(canAdvance({ ...initialState, name: '   ' })).toBe(false)
  })

  it('step 1: false when nameError set', () => {
    expect(canAdvance({ ...initialState, name: 'demo', nameError: '冲突' })).toBe(false)
  })

  it('step 1: true when name >= 2 + no error', () => {
    expect(canAdvance({ ...initialState, name: 'demo' })).toBe(true)
  })

  it('step 2: false when no datasource selected', () => {
    expect(canAdvance({ ...initialState, step: 2 })).toBe(false)
  })

  it('step 2: true when ≥1 selected', () => {
    expect(canAdvance({
      ...initialState, step: 2, selectedTypes: ['github'],
    })).toBe(true)
  })

  it('step 3: false when no datasource added', () => {
    expect(canAdvance({ ...initialState, step: 3 })).toBe(false)
  })

  it('step 3: true when ≥1 added', () => {
    expect(canAdvance({
      ...initialState, step: 3, addedDatasources: [mockDatasource],
    })).toBe(true)
  })

  it('step 4: always true', () => {
    expect(canAdvance({ ...initialState, step: 4 })).toBe(true)
  })

  it('unknown step: false (default)', () => {
    // @ts-expect-error - 故意越界
    expect(canAdvance({ ...initialState, step: 99 })).toBe(false)
  })
})


describe('STEP_TITLES', () => {
  it('has 4 step titles', () => {
    expect(STEP_TITLES[1]).toBe('基本信息')
    expect(STEP_TITLES[2]).toBe('选择数据源')
    expect(STEP_TITLES[3]).toBe('接入指引')
    expect(STEP_TITLES[4]).toBe('完成')
  })
})
