/**
 * DocSidebar · 右侧栏 (证据 / 评论 / 历史版本 tabs)
 *
 * Phase 1: 占位 Tabs + 元数据卡
 * Phase 3 / T07: 证据 tab 接入真证据数据
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BookText, MessageSquare, History } from 'lucide-react'
import { EmptyState } from '@/components/shared/EmptyState'
import type { Asset } from '@/types/api'

interface DocSidebarProps {
  asset: Asset
}

export function DocSidebar({ asset }: DocSidebarProps) {
  return (
    <aside
      className="flex h-full flex-col gap-4 overflow-auto border-l border-border-subtle bg-bg-card p-4"
      aria-label="文档侧栏"
    >
      <section className="space-y-2">
        <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
          元数据
        </p>
        <dl className="space-y-1.5 text-body-sm">
          <Row label="模板">{asset.template_id ?? '—'}</Row>
          <Row label="创建于">
            {new Date(asset.created_at).toLocaleString('zh-CN', { hour12: false })}
          </Row>
          <Row label="更新于">
            {new Date(asset.updated_at).toLocaleString('zh-CN', { hour12: false })}
          </Row>
          <Row label="审批">{asset.approval_state}</Row>
          <Row label="脱敏">
            {asset.redaction_state === 'all_confirmed' ? '✅ 全部确认' : '⚠ 待确认'}
          </Row>
        </dl>
      </section>

      <Tabs defaultValue="evidence" className="flex-1 flex flex-col">
        <TabsList className="grid grid-cols-3">
          <TabsTrigger value="evidence" className="font-ui text-caption">
            <BookText className="size-3.5" />
            证据
          </TabsTrigger>
          <TabsTrigger value="comments" className="font-ui text-caption">
            <MessageSquare className="size-3.5" />
            评论
          </TabsTrigger>
          <TabsTrigger value="history" className="font-ui text-caption">
            <History className="size-3.5" />
            历史
          </TabsTrigger>
        </TabsList>
        <TabsContent value="evidence" className="flex-1">
          <EmptyState
            title="点击章节内 [N] 角标"
            description="证据链抽屉 (T07) 会展示该段落引用的原始 PR / 对话片段。"
          />
        </TabsContent>
        <TabsContent value="comments" className="flex-1">
          <EmptyState
            title="批注待 T09 实现"
            description="进入审批后, Reviewer 可对每段添加批注。"
          />
        </TabsContent>
        <TabsContent value="history" className="flex-1">
          <EmptyState
            title="版本历史"
            description={`当前 v${asset.current_version}。每次发布会冻结快照。`}
          />
        </TabsContent>
      </Tabs>
    </aside>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[60px_1fr] items-baseline gap-2">
      <dt className="font-ui text-caption text-text-muted">{label}</dt>
      <dd className="font-ui text-caption text-text-primary truncate">{children}</dd>
    </div>
  )
}
