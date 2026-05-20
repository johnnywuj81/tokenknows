/**
 * T02 项目向导状态机 · useReducer
 *
 * 决策来源 TaskTechDesign T02:
 *   "向导 state 用 useReducer 不用 Zustand。状态机有限(4 步 + 选中的数据源),
 *    无需跨页持久化;用户中途关掉浏览器再回来就重新开始,**故意不 persist**。"
 */

import type { Datasource, DatasourceType, Project } from '@/types/api'

export type WizardStep = 1 | 2 | 3 | 4

export interface WizardState {
  step: WizardStep
  // Step 1 · 基本信息
  name: string
  description: string
  nameError: string | null      // 409 重名错误
  // Step 2 · 数据源类型选择
  selectedTypes: DatasourceType[]
  // Step 3 · 接入指引(submit step 2 后已创建 project)
  createdProject: Project | null
  addedDatasources: Datasource[]
}

export type WizardAction =
  | { type: 'SET_NAME'; value: string }
  | { type: 'SET_DESCRIPTION'; value: string }
  | { type: 'TOGGLE_DATASOURCE'; ds: DatasourceType }
  | { type: 'NAME_CONFLICT'; message: string }
  | { type: 'CLEAR_NAME_ERROR' }
  | { type: 'PROJECT_CREATED'; project: Project }
  | { type: 'DATASOURCE_ADDED'; ds: Datasource }
  | { type: 'GO_NEXT' }
  | { type: 'GO_PREV' }
  | { type: 'GO_TO'; step: WizardStep }

export const initialState: WizardState = {
  step: 1,
  name: '',
  description: '',
  nameError: null,
  selectedTypes: [],
  createdProject: null,
  addedDatasources: [],
}

export function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'SET_NAME':
      return { ...state, name: action.value, nameError: null }
    case 'SET_DESCRIPTION':
      return { ...state, description: action.value }
    case 'TOGGLE_DATASOURCE': {
      const has = state.selectedTypes.includes(action.ds)
      return {
        ...state,
        selectedTypes: has
          ? state.selectedTypes.filter((x) => x !== action.ds)
          : [...state.selectedTypes, action.ds],
      }
    }
    case 'NAME_CONFLICT':
      return { ...state, nameError: action.message, step: 1 }
    case 'CLEAR_NAME_ERROR':
      return { ...state, nameError: null }
    case 'PROJECT_CREATED':
      return { ...state, createdProject: action.project }
    case 'DATASOURCE_ADDED':
      return { ...state, addedDatasources: [...state.addedDatasources, action.ds] }
    case 'GO_NEXT':
      return { ...state, step: Math.min(4, state.step + 1) as WizardStep }
    case 'GO_PREV':
      return { ...state, step: Math.max(1, state.step - 1) as WizardStep }
    case 'GO_TO':
      return { ...state, step: action.step }
    default:
      return state
  }
}

/** 步骤 schema(简单本地校验, zod 用在 form 里) */
export function canAdvance(state: WizardState): boolean {
  switch (state.step) {
    case 1:
      return state.name.trim().length >= 2 && !state.nameError
    case 2:
      return state.selectedTypes.length >= 1
    case 3:
      // 至少完成 1 个数据源(为 demo 体验放宽,真实可要求所有 selected 全部接入)
      return state.addedDatasources.length >= 1
    case 4:
      return true
    default:
      return false
  }
}

export const STEP_TITLES: Record<WizardStep, string> = {
  1: '基本信息',
  2: '选择数据源',
  3: '接入指引',
  4: '完成',
}
