/**
 * NodeCrossDocPanel · v1.3.1 T96 · 节点 click 时显示的跨文档实体面板.
 *
 * 行为:
 *   - 节点未选 / 未注册 entity → 不显示
 *   - 显示该 entity 出现的其他 asset 列表 (除当前 asset)
 *   - 点击 asset → useNavigate 跳转到该 asset 的 DocumentPage
 *   - 同 asset 内只显示 aliases (不算跨文档)
 */

import { useNavigate } from 'react-router-dom'
import { Link2, X, Layers } from 'lucide-react'
import type { KGNode } from '@/types/api'
import { useNodeEntity } from './hooks/useNodeEntity'

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

  if (!node) return null

  const entity = query.data?.entity
  const sources = query.data?.sources ?? []
  const otherDocs = sources.filter((s) => s.asset_id !== assetId)

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
