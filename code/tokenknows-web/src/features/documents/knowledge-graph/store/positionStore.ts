/**
 * positionStore · v1.2.1 T90 · 节点拖动本地持久化.
 *
 * 用 Zustand 全局 store + zustand/middleware/persist 把每个 asset 的
 * 节点位置存到 localStorage (key=tokenknows_kg_positions).
 *
 * 行为:
 *   - GraphCanvas 监听 onNodeDragStop → setPosition(assetId, nodeId, {x, y})
 *   - 首次渲染时优先用 store 中的坐标, 否则回退 dagre 自动布局
 *   - 刷新页面后位置保持
 *
 * 注: MVP 仅本地; 不回写后端 (chapter.layout.user_positions). v1.3 加 PATCH.
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
