/**
 * IMChatsPage · /projects/:id/datasources/im/connections/:cid/chats (v0.3 T25)
 *
 * MVP 实现:
 * - 左栏: 可见群列表 (来自 list_chats)
 * - 右栏: 选中群的统计卡片 (消息数 / signal 数 / TOP 3 contributors)
 * - 单条操作: 邀请 bot 入群 / 触发蒸馏
 *
 * 不在 MVP 内:
 * - SSE 实时刷新 (用户手动 refresh)
 * - SignalGate 阈值调节 UI (留 v0.3.1)
 */

import { useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronLeft, MessageSquarePlus, Sparkles, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import {
  useChatStats,
  useDistillIMChat,
  useIMChats,
  useJoinChat,
} from './hooks/useIMConnections'
import type { IMChat } from '@/types/api'

export default function IMChatsPage() {
  const { id: projectId = '', cid: connectionId = '' } = useParams<{
    id: string
    cid: string
  }>()
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const chats = useIMChats(connectionId)
  const join = useJoinChat(connectionId)
  const distill = useDistillIMChat(connectionId)
  const stats = useChatStats(connectionId, selectedChatId)

  const sortedChats = useMemo(() => {
    return [...(chats.data ?? [])].sort((a, b) =>
      (a.name ?? '').localeCompare(b.name ?? ''),
    )
  }, [chats.data])

  if (chats.isLoading) return <LoadingSkeleton variant="list" />
  if (chats.isError) {
    return (
      <ErrorState
        title="加载群列表失败"
        description="可能 access_token 已过期,请回到 IM 数据源页重连"
        onRetry={() => chats.refetch()}
      />
    )
  }

  const handleJoin = (chatId: string) => {
    join.mutate(chatId)
  }

  const handleDistill = (chatId: string) => {
    distill.mutate({ chat_id: chatId, source_mode: 'assistant' })
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/projects/${projectId}/datasources`}>
            <ChevronLeft className="size-4" />
            返回
          </Link>
        </Button>
        <div>
          <h1 className="font-content text-2xl font-semibold text-text-primary">
            管理群 & 统计
          </h1>
          <p className="font-ui text-sm text-text-secondary">
            选择群 → 邀请 bot 入群 → 蒸馏对话价值片段
          </p>
        </div>
      </header>

      {sortedChats.length === 0 ? (
        <EmptyState
          title="该 connection 暂无可见群"
          description="确保 OAuth 授权范围包含 im:chat,然后回到 IM 数据源页查看"
        />
      ) : (
        <div className="grid grid-cols-[360px_1fr] gap-4">
          <ChatList
            chats={sortedChats}
            selectedChatId={selectedChatId}
            onSelect={setSelectedChatId}
            onJoin={handleJoin}
            joining={join.isPending}
          />
          {selectedChatId ? (
            <ChatDetail
              chatId={selectedChatId}
              stats={stats.data}
              loading={stats.isLoading}
              onDistill={() => handleDistill(selectedChatId)}
              distilling={distill.isPending}
              distillResult={distill.data}
            />
          ) : (
            <EmptyState
              title="选中一个群查看统计"
              description="左侧任选一条"
            />
          )}
        </div>
      )}
    </div>
  )
}

interface ChatListProps {
  chats: IMChat[]
  selectedChatId: string | null
  onSelect: (chatId: string) => void
  onJoin: (chatId: string) => void
  joining: boolean
}

function ChatList({
  chats,
  selectedChatId,
  onSelect,
  onJoin,
  joining,
}: ChatListProps) {
  return (
    <div className="flex flex-col gap-2">
      {chats.map((c) => {
        const chatId = (c.chat_id as string) ?? ''
        if (!chatId) return null
        const active = chatId === selectedChatId
        return (
          <Card
            key={chatId}
            onClick={() => onSelect(chatId)}
            className={`flex cursor-pointer items-start justify-between gap-2 p-3 transition-colors ${
              active ? 'border-accent-primary bg-bg-card-hover' : 'hover:bg-bg-warm'
            }`}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate font-content text-base font-medium text-text-primary">
                {c.name ?? chatId}
              </p>
              <p className="font-ui text-xs text-text-tertiary">
                {c.chat_type ?? 'group'} · {chatId}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onJoin(chatId)
              }}
              disabled={joining}
              title="邀请 bot 入群"
            >
              <MessageSquarePlus className="size-4" />
            </Button>
          </Card>
        )
      })}
    </div>
  )
}

interface ChatDetailProps {
  chatId: string
  stats: import('@/types/api').IMChatStats | undefined
  loading: boolean
  onDistill: () => void
  distilling: boolean
  distillResult: import('@/types/api').DistillIMResponse | undefined
}

function ChatDetail({
  chatId,
  stats,
  loading,
  onDistill,
  distilling,
  distillResult,
}: ChatDetailProps) {
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-content text-xl font-semibold text-text-primary">
          {chatId}
        </h2>
        <Button onClick={onDistill} disabled={distilling}>
          <Sparkles className="size-4" />
          {distilling ? '蒸馏中...' : '触发蒸馏'}
        </Button>
      </div>

      {loading ? (
        <LoadingSkeleton variant="form" />
      ) : stats ? (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="消息数" value={stats.message_count} />
          <StatCard label="Signal 数" value={stats.signal_count} />
          <StatCard
            label="信号率"
            value={`${Math.round(stats.signal_rate * 100)}%`}
          />
        </div>
      ) : (
        <p className="text-sm text-text-tertiary">暂无统计数据</p>
      )}

      <section>
        <h3 className="font-ui mb-2 flex items-center gap-1 text-sm font-medium text-text-secondary">
          <Users className="size-4" />
          TOP Contributors
        </h3>
        {stats?.top_contributors && stats.top_contributors.length > 0 ? (
          <ol className="space-y-1 text-sm">
            {stats.top_contributors.map((u, i) => (
              <li
                key={u.user_id}
                className="flex items-center justify-between rounded px-2 py-1 text-text-primary hover:bg-bg-warm"
              >
                <span>
                  {i + 1}. {u.name ?? u.user_id}
                </span>
                <span className="font-mono text-xs text-text-tertiary">
                  {u.messages} 条
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-text-tertiary">暂无贡献者数据</p>
        )}
      </section>

      {distillResult && (
        <div
          role="status"
          className="rounded border-l-4 border-l-success bg-success-light/40 px-3 py-2 font-ui text-sm text-success-dark"
        >
          蒸馏完成 · 写入 {distillResult.segments_persisted} 个 ValueSegment
        </div>
      )}
    </Card>
  )
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-bg-card p-3">
      <p className="font-ui text-xs uppercase tracking-wide text-text-tertiary">
        {label}
      </p>
      <p className="mt-1 font-content text-2xl font-semibold text-text-primary">
        {value}
      </p>
    </div>
  )
}
