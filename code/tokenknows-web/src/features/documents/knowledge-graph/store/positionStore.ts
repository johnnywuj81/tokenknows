/**
 * positionStore · v1.2.1 T90 / v1.3 T91 · 节点拖动位置本地缓存.
 *
 * 用 Zustand 全局 store + zustand/middleware/persist 把每个 asset 的
 * 节点位置存到 localStorage (key=tokenknows_kg_positions).
 *
 * 优先级 (GraphCanvas 用): `layout.user_positions` (server) > store (local) > dagre 自动.
 *
 * 行为:
 *   - GraphCanvas 监听 onNodeDragStop → setPosition(assetId, nodeId, {x, y})
 *     同时通过 useChapterPositionsSync debounced PATCH 写后端 (T91)
 *   - 首次渲染时若 server 已有 user_positions, 调用 hydrateAsset 同步到 store
 *     避免本地 store 与 server 永久 drift
 *   - 离线 / 无 chapterId 场景, store 仅本地, 刷新页面后位置不丢
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface NodePosition {
  x: number
  y: number
}

interface PositionState {
  /** assetId → { nodeId: {x, y} } */
  positions: Record<string, Record<string, NodePosition>>
  setPosition: (assetId: string, nodeId: string, pos: NodePosition) => void
  /** v1.3 T91 · 整体 hydrate (server snapshot → store). 用于跨设备同步. */
  hydrateAsset: (assetId: string, positions: Record<string, NodePosition>) => void
  getPositions: (assetId: string) => Record<string, NodePosition>
  clearAsset: (assetId: string) => void
}

export const usePositionStore = create<PositionState>()(
  persist(
    (set, get) => ({
      positions: {},
      setPosition: (assetId, nodeId, pos) =>
        set((state) => ({
          positions: {
            ...state.positions,
            [assetId]: {
              ...(state.positions[assetId] || {}),
              [nodeId]: pos,
            },
          },
        })),
      hydrateAsset: (assetId, positions) =>
        set((state) => ({
          positions: {
            ...state.positions,
            [assetId]: { ...positions },
          },
        })),
      getPositions: (assetId) => get().positions[assetId] || {},
      clearAsset: (assetId) =>
        set((state) => {
          const next = { ...state.positions }
          delete next[assetId]
          return { positions: next }
        }),
    }),
    {
      name: 'tokenknows_kg_positions',
      // 仅持久化 positions, 跳过 actions (默认行为)
    },
  ),
)
