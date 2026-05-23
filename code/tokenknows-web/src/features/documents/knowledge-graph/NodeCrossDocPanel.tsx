/**
 * NodeCrossDocPanel · v1.3.1 T96 / v1.5 T98 · 节点 click 时显示的跨文档实体面板.
 *
 * 行为:
 *   - 节点未选 / 未注册 entity → 不显示
 *   - 显示该 entity 出现的其他 asset 列表 (除当前 asset)
 *   - 点击 asset → useNavigate 跳转到该 asset 的 DocumentPage
 *   - 同 asset 内只显示 aliases (不算跨文档)
 *   - T98: entity 含 >1 个 ref 时显示 "拆出此节点" 按钮 (语义纠错)
 */

import { useNavigate } from 'react-router-dom'
import { Link2, X, Layers, Scissors, Globe2, Upload } from 'lucide-react'
import type { KGNode } from '@/types/api'
import {
  useNodeEntity,
  useSplitNode,
  useGlobalEntityForProjectEntity,
  usePublishEntityToGlobal,
  useUnlinkEntityFromGlobal,
} from './hooks/useNodeEntity'

interface NodeCrossDocPanelProps {
  /** 当前 asset id (排除自身). */
  assetId: string
  /** 当前选中的 node, null 时面板不显示. */
  node: KGNode | null
  /** project_id 用于导航 URL. */
  projectId: string
  onClose: () => void
}

export function NodeCrossDocPanel({
  assetId,
  node,
  projectId,
  onClose,
}: NodeCrossDocPanelProps) {
  const nodeId = node?.id ?? null
  const query = useNodeEntity(assetId, nodeId)
  const navigate = useNavigate()
  const splitMutation = useSplitNode()
  // T99: global entity 查询 + publish/unlink
  const projectEntityId = query.data?.entity?.id ?? null
  const globalQuery = useGlobalEntityForProjectEntity(projectEntityId)
  const publishMutation = usePublishEntityToGlobal()
  const unlinkMutation = useUnlinkEntityFromGlobal()

  if (!node) return null

  const entity = query.data?.entity
  const sources = query.data?.sources ?? []
  const otherDocs = sources.filter((s) => s.asset_id !== assetId)
  // T98: entity 有 >1 个 ref 才能拆 (单 ref 拆 = rename, 后端 422 拒绝)
  const canSplit = !!(entity && entity.source_refs.length > 1)
  const globalEntity = globalQuery.data ?? null

  function handleSplit() {
    if (!entity || !nodeId) return
    splitMutation.mutate({
      entityId: entity.id,
      assetId,
      nodeId,
      newLabel: `${node.label} (split)`,
    })
  }

  function handlePublishGlobal() {
    if (!entity) return
    publishMutation.mutate(entity.id)
  }

  function handleUnlinkGlobal() {
    if (!entity) return
    unlinkMutation.mutate(entity.id)
  }

  return (
    <div
      data-testid="kg-cross-doc-panel"
      className="rounded-lg border border-border-subtle bg-bg-card shadow-elev-1 p-4 max-w-sm"
    >
      <header className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
            实体跨文档关联
          </p>
          <h4 className="font-content text-h4 text-text-primary mt-0.5 line-clamp-1">
            {node.label}
          </h4>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭面板"
          className="rounded p-1 text-text-muted hover:bg-bg-warm hover:text-text-primary"
        >
          <X className="size-3.5" />
        </button>
      </header>

      {query.isLoading ? (
        <p className="font-ui text-caption text-text-muted">加载中…</p>
      ) : !entity ? (
        <p
          className="font-ui text-caption text-text-muted"
          data-testid="kg-cross-doc-empty"
        >
          该节点尚未关联实体 (未跑 assess 阶段)
        </p>
      ) : (
        <>
          {entity.aliases.length > 0 ? (
            <div className="mb-3 flex items-start gap-1.5 text-caption">
              <Layers className="mt-0.5 size-3 shrink-0 text-text-subtle" />
              <div className="font-ui text-text-muted">
                也称: <span className="text-text-secondary">{entity.aliases.join(', ')}</span>
              </div>
            </div>
          ) : null}

          {canSplit ? (
            <button
              type="button"
              data-testid="kg-cross-doc-split-btn"
              onClick={handleSplit}
              disabled={splitMutation.isPending}
              className="mb-3 flex w-full items-center justify-center gap-1.5 rounded border border-warning bg-warning-bg px-2 py-1.5 font-ui text-caption text-warning-dark hover:bg-warning-bg/80 disabled:opacity-50 transition"
              title="拆出此节点 — 实际是不同实体, assess 误合"
            >
              <Scissors className="size-3" />
              {splitMutation.isPending ? '拆分中…' : '拆出此节点 (不是同一实体)'}
            </button>
          ) : null}

          {/* v1.5 T99 · 跨 project global entity 区 */}
          <div
            data-testid="kg-cross-doc-global"
            className="mb-3 rounded border border-info bg-info-bg/50 p-2"
          >
            <div className="mb-1 flex items-center gap-1 font-ui text-micro font-medium text-info-dark uppercase tracking-wider">
              <Globe2 className="size-3" />
              全局实体
            </div>
            {globalQuery.isLoading ? (
              <p className="font-ui text-caption text-text-muted">加载中…</p>
            ) : globalEntity ? (
              <>
                <p
                  className="font-ui text-caption text-text-secondary"
                  data-testid="kg-cross-doc-global-info"
                >
                  已发布 · 跨 <strong className="font-mono">{globalEntity.project_count}</strong> 个 project
                </p>
                <button
                  type="button"
                  data-testid="kg-cross-doc-unlink-global-btn"
                  onClick={handleUnlinkGlobal}
                  disabled={unlinkMutation.isPending}
                  className="mt-1 font-ui text-micro text-text-muted hover:underline disabled:opacity-50"
                >
                  {unlinkMutation.isPending ? '解除中…' : '从全局解除关联'}
                </button>
              </>
            ) : (
              <>
                <p className="font-ui text-caption text-text-muted">
                  尚未发布到 project 间共享
                </p>
                <button
                  type="button"
                  data-testid="kg-cross-doc-publish-global-btn"
                  onClick={handlePublishGlobal}
                  disabled={publishMutation.isPending}
                  className="mt-1 flex items-center gap-1 font-ui text-caption text-info-dark hover:underline disabled:opacity-50"
                >
                  <Upload className="size-3" />
                  {publishMutation.isPending ? '发布中…' : '发布到全局'}
                </button>
              </>
            )}
          </div>

          {otherDocs.length === 0 ? (
            <p
              className="font-ui text-caption text-text-muted"
              data-testid="kg-cross-doc-only-here"
            >
              该实体仅出现在当前文档
            </p>
          ) : (
            <>
              <p className="mb-1.5 font-ui text-caption text-text-muted">
                也出现在 <strong className="font-mono text-text-secondary">{otherDocs.length}</strong> 个其他文档:
              </p>
              <ul className="space-y-1">
                {otherDocs.map((doc) => (
                  <li key={doc.asset_id}>
                    <button
                      type="button"
                      data-testid={`kg-cross-doc-link-${doc.asset_id}`}
                      onClick={() => {
                        navigate(`/projects/${projectId}/documents/${doc.asset_id}`)
                      }}
                      className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left font-ui text-body-sm text-accent-primary-dark hover:bg-bg-warm transition"
                    >
                      <Link2 className="size-3 shrink-0" />
                      <span className="line-clamp-1 flex-1">{doc.asset_title}</span>
                      <span className="font-mono text-micro text-text-subtle">
                        {doc.node_ids.length}n
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
