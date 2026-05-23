/**
 * positionStore · v1.2.1 T90 unit tests.
 *
 * 验:
 *   - setPosition / getPositions 基础读写
 *   - 跨 assetId 隔离
 *   - clearAsset 不影响其他 asset
 *   - localStorage 持久化 (mock storage)
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { usePositionStore } from './positionStore'

beforeEach(() => {
  // 清空 store + localStorage
  usePositionStore.setState({ positions: {} })
  if (typeof localStorage !== 'undefined') {
    localStorage.clear()
  }
})

describe('positionStore', () => {
  it('初始为空对象', () => {
    expect(usePositionStore.getState().getPositions('a-1')).toEqual({})
  })

  it('setPosition 写入后 getPositions 读到', () => {
    usePositionStore.getState().setPosition('a-1', 'n_alice', { x: 100, y: 200 })
    const positions = usePositionStore.getState().getPositions('a-1')
    expect(positions['n_alice']).toEqual({ x: 100, y: 200 })
  })

  it('跨 assetId 隔离', () => {
    usePositionStore.getState().setPosition('a-1', 'n_x', { x: 10, y: 20 })
    usePositionStore.getState().setPosition('a-2', 'n_y', { x: 30, y: 40 })
    expect(usePositionStore.getState().getPositions('a-1')['n_x']).toEqual({
      x: 10, y: 20,
    })
    expect(usePositionStore.getState().getPositions('a-2')['n_y']).toEqual({
      x: 30, y: 40,
    })
    expect(usePositionStore.getState().getPositions('a-1')['n_y']).toBeUndefined()
  })

  it('多个节点位置在同一 assetId 下并存', () => {
    usePositionStore.getState().setPosition('a-1', 'n_a', { x: 1, y: 1 })
    usePositionStore.getState().setPosition('a-1', 'n_b', { x: 2, y: 2 })
    usePositionStore.getState().setPosition('a-1', 'n_c', { x: 3, y: 3 })
    const positions = usePositionStore.getState().getPositions('a-1')
    expect(Object.keys(positions)).toHaveLength(3)
  })

  it('setPosition 同 nodeId 覆盖', () => {
    usePositionStore.getState().setPosition('a-1', 'n_a', { x: 1, y: 1 })
    usePositionStore.getState().setPosition('a-1', 'n_a', { x: 99, y: 99 })
    expect(usePositionStore.getState().getPositions('a-1')['n_a']).toEqual({
      x: 99, y: 99,
    })
  })

  it('clearAsset 清空指定 asset 不影响其他', () => {
    usePositionStore.getState().setPosition('a-1', 'n_x', { x: 10, y: 20 })
    usePositionStore.getState().setPosition('a-2', 'n_y', { x: 30, y: 40 })
    usePositionStore.getState().clearAsset('a-1')
    expect(usePositionStore.getState().getPositions('a-1')).toEqual({})
    expect(usePositionStore.getState().getPositions('a-2')['n_y']).toEqual({
      x: 30, y: 40,
    })
  })

  it('zustand persist 写入 localStorage', () => {
    usePositionStore.getState().setPosition('a-1', 'n_x', { x: 50, y: 75 })
    // zustand persist key
    const raw = localStorage.getItem('tokenknows_kg_positions')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!) as {
      state: { positions: Record<string, Record<string, { x: number; y: number }>> }
    }
    expect(parsed.state.positions['a-1']['n_x']).toEqual({ x: 50, y: 75 })
  })
})
