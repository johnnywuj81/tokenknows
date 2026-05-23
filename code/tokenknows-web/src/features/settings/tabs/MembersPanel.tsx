/**
 * MembersPanel · v0.9.0 T67 项目成员管理.
 *
 * 仅 owner 可改 (后端 ACL 兜底); UI 仅控可视, 非 owner 隐藏写按钮.
 */

import { useState } from 'react'
import type { ProjectMember, ProjectMemberRole } from '@/types/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuthStore } from '@/stores/authStore'
import {
  useAddMember,
  useProjectMembers,
  useRemoveMember,
  useUpdateMemberRole,
} from '../hooks/useMembers'

interface MembersPanelProps {
  projectId: string
}

const ROLE_LABELS: Record<ProjectMemberRole, string> = {
  owner: 'Owner',
  reviewer: 'Reviewer',
  contributor: 'Contributor',
}

const ROLE_COLORS: Record<ProjectMemberRole, string> = {
  owner: 'bg-accent-primary-light text-accent-primary-dark',
  reviewer: 'bg-success-bg text-success-dark',
  contributor: 'bg-bg-warm text-text-muted',
}

export function MembersPanel({ projectId }: MembersPanelProps) {
  const currentUserId = useAuthStore((s) => s.user?.id ?? null)
  const q = useProjectMembers(projectId)

  if (q.isLoading) {
    return <p className="text-sm text-text-secondary">加载中...</p>
  }
  if (q.isError || !q.data) {
    return (
      <p className="text-sm text-danger">
        加载成员失败. <button onClick={() => q.refetch()}>重试</button>
      </p>
    )
  }

  const data = q.data
  const iAmOwner = !!(
    currentUserId &&
    data.items.some(
      (m) => m.user_id === currentUserId && m.role === 'owner',
    )
  )
  const isEmpty = data.items.length === 0

  return (
    <section className="space-y-4" data-testid="members-panel">
      <header>
        <h2 className="font-content text-h2 text-text-primary">成员管理</h2>
        <p className="font-ui text-caption text-text-muted">
          {iAmOwner ? '你是 owner, 可添加/编辑/移除成员.' : '只读模式 (仅 owner 可改).'}
        </p>
      </header>

      <div className="grid grid-cols-3 gap-2">
        <StatChip label="Owner" count={data.owner_count} color="primary" />
        <StatChip label="Reviewer" count={data.reviewer_count} color="success" />
        <StatChip label="Contributor" count={data.contributor_count} />
      </div>

      {/* Bootstrap CTA (空项目) */}
      {isEmpty && (
        <BootstrapCard projectId={projectId} currentUserId={currentUserId} />
      )}

      {/* 成员列表 */}
      {!isEmpty && (
        <div
          className="overflow-hidden rounded-md border border-border-subtle bg-bg-card"
          data-testid="members-table"
        >
          <table className="w-full font-ui text-body-sm">
            <thead className="border-b border-border-subtle bg-bg-warm">
              <tr className="text-left text-caption text-text-muted">
                <th className="px-3 py-2">User ID</th>
                <th className="px-3 py-2">角色</th>
                <th className="px-3 py-2">加入时间</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((m) => (
                <MemberRow
                  key={m.id}
                  member={m}
                  projectId={projectId}
                  iAmOwner={iAmOwner}
                  currentUserId={currentUserId}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {iAmOwner && !isEmpty && (
        <AddMemberForm projectId={projectId} />
      )}
    </section>
  )
}

// ─── Subcomponents ──────────────────────────────────────────


function StatChip({
  label,
  count,
  color,
}: {
  label: string
  count: number
  color?: 'primary' | 'success'
}) {
  const colorClass =
    color === 'primary'
      ? 'text-accent-primary-dark'
      : color === 'success'
        ? 'text-success-dark'
        : 'text-text-primary'
  return (
    <div className="rounded-md border border-border-subtle p-3">
      <p className="font-ui text-caption text-text-muted">{label}</p>
      <p className={`mt-1 font-content text-xl font-semibold ${colorClass}`}>
        {count}
      </p>
    </div>
  )
}


function BootstrapCard({
  projectId,
  currentUserId,
}: {
  projectId: string
  currentUserId: string | null
}) {
  const addMember = useAddMember(projectId)
  const [error, setError] = useState<string | null>(null)

  async function handleBootstrap(): Promise<void> {
    setError(null)
    if (!currentUserId) {
      setError('请先登录')
      return
    }
    try {
      await addMember.mutateAsync({
        user_id: currentUserId,
        role: 'owner',
      })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '初始化失败')
    }
  }

  return (
    <div
      className="rounded-md border border-warning bg-warning-bg p-4"
      data-testid="members-bootstrap"
    >
      <p className="font-ui text-sm font-medium text-warning-dark">
        ⚠ 项目尚未配置成员
      </p>
      <p className="mt-1 text-xs text-text-secondary">
        没有 owner, 任何人都能改 (兼容老行为). 点击下方按钮把自己设为 owner 启用 ACL.
      </p>
      <div className="mt-3">
        <Button
          size="sm"
          onClick={handleBootstrap}
          disabled={addMember.isPending}
          data-testid="bootstrap-owner-btn"
        >
          {addMember.isPending ? '初始化中...' : '我来做 owner'}
        </Button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-danger" data-testid="bootstrap-error">
          {error}
        </p>
      )}
    </div>
  )
}


function MemberRow({
  member,
  projectId,
  iAmOwner,
  currentUserId,
}: {
  member: ProjectMember
  projectId: string
  iAmOwner: boolean
  currentUserId: string | null
}) {
  const updateRole = useUpdateMemberRole(projectId)
  const removeMember = useRemoveMember(projectId)
  const isSelf = currentUserId === member.user_id
  return (
    <tr
      className="border-b border-border-subtle last:border-b-0"
      data-testid={`member-row-${member.user_id}`}
    >
      <td className="px-3 py-2 font-mono text-text-primary">
        {member.user_id}
        {isSelf && (
          <span className="ml-1 font-mono text-[10px] text-text-tertiary">
            (你)
          </span>
        )}
      </td>
      <td className="px-3 py-2">
        {iAmOwner ? (
          <select
            value={member.role}
            onChange={(e) =>
              updateRole.mutate({
                userId: member.user_id,
                role: e.target.value as ProjectMemberRole,
              })
            }
            disabled={updateRole.isPending}
            data-testid={`role-select-${member.user_id}`}
            className="rounded border border-border-subtle bg-bg-card px-2 py-1 font-ui text-body-sm"
          >
            <option value="owner">{ROLE_LABELS.owner}</option>
            <option value="reviewer">{ROLE_LABELS.reviewer}</option>
            <option value="contributor">{ROLE_LABELS.contributor}</option>
          </select>
        ) : (
          <span
            className={`rounded-full px-2 py-0.5 font-ui text-micro ${
              ROLE_COLORS[member.role]
            }`}
          >
            {ROLE_LABELS[member.role]}
          </span>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-caption text-text-subtle">
        {new Date(member.added_at).toLocaleDateString('zh-CN')}
      </td>
      <td className="px-3 py-2">
        {iAmOwner ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => removeMember.mutate(member.user_id)}
            disabled={removeMember.isPending}
            data-testid={`remove-${member.user_id}`}
          >
            移除
          </Button>
        ) : null}
      </td>
    </tr>
  )
}


function AddMemberForm({ projectId }: { projectId: string }) {
  const addMember = useAddMember(projectId)
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<ProjectMemberRole>('contributor')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    if (!userId.trim()) {
      setError('请输入 user_id')
      return
    }
    try {
      await addMember.mutateAsync({ user_id: userId.trim(), role })
      setUserId('')
      setRole('contributor')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '添加失败')
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-canvas p-3 sm:flex-row sm:items-center"
      data-testid="add-member-form"
    >
      <Input
        type="text"
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        placeholder="user_id (platform open_id / userid)"
        data-testid="add-member-user-id"
        className="flex-1"
      />
      <select
        value={role}
        onChange={(e) => setRole(e.target.value as ProjectMemberRole)}
        data-testid="add-member-role"
        className="rounded border border-border-subtle bg-bg-card px-2 py-1 font-ui text-body-sm"
      >
        <option value="contributor">{ROLE_LABELS.contributor}</option>
        <option value="reviewer">{ROLE_LABELS.reviewer}</option>
        <option value="owner">{ROLE_LABELS.owner}</option>
      </select>
      <Button
        type="submit"
        size="sm"
        disabled={addMember.isPending}
        data-testid="add-member-submit"
      >
        {addMember.isPending ? '添加中...' : '+ 添加成员'}
      </Button>
      {error && (
        <p className="text-xs text-danger" data-testid="add-member-error">
          {error}
        </p>
      )}
    </form>
  )
}
