/**
 * T03 · WorkbenchPage
 *
 * 三栏布局:
 *   [左] ProjectStats(项目卡 + 4 数字卡)
 *   [中] EventStream(实时事件流, 30s polling)
 *   [右] TodoList(本周待办)
 *
 * URL ↔ store 同步:
 *   - /projects/:id → setCurrent(:id)
 *   - / 无 :id → 用 store 里 currentProjectId, 若都没有 → EmptyWorkbench
 */

import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useProjectStore } from '@/stores/projectStore'
import { useProject } from './hooks/useProject'
import { useProjectStats } from './hooks/useProjectStats'
import { useTodos } from './hooks/useTodos'
import { useProjects } from './hooks/useProjects'
import { ProjectStats } from './components/ProjectStats'
import { EventStream } from './components/EventStream'
import { TodoList } from './components/TodoList'
import { EmptyWorkbench } from './components/EmptyWorkbench'
import { ErrorState } from '@/components/shared/ErrorState'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'

export default function WorkbenchPage() {
  const { id: paramId } = useParams<{ id?: string }>()
  const currentProjectId = useProjectStore((s) => s.currentProjectId)
  const setCurrent = useProjectStore((s) => s.setCurrent)

  // URL → store 同步(URL 优先)
  useEffect(() => {
    if (paramId && paramId !== currentProjectId) {
      setCurrent(paramId)
    }
  }, [paramId, currentProjectId, setCurrent])

  const projectId = paramId ?? currentProjectId
  const projectsQuery = useProjects()
  const projectQuery = useProject(projectId)
  const statsQuery = useProjectStats(projectId)
  const todosQuery = useTodos(projectId)

  // 无项目可显示
  if (!projectId) {
    // 等待项目列表加载完成
    if (projectsQuery.isLoading) {
      return <LoadingSkeleton variant="workbench" />
    }
    if (projectsQuery.error) {
      return (
        <ErrorState
          variant="fullscreen"
          title="加载项目失败"
          error={projectsQuery.error}
          onRetry={() => projectsQuery.refetch()}
        />
      )
    }
    if ((projectsQuery.data?.length ?? 0) === 0) {
      return <EmptyWorkbench />
    }
    // 有项目但未选中 → 自动选第一个
    return <AutoSelectFirst onSelect={setCurrent} firstId={projectsQuery.data?.[0]?.id ?? null} />
  }

  // 项目级错误
  if (projectQuery.error) {
    return (
      <ErrorState
        variant="fullscreen"
        title="项目加载失败"
        error={projectQuery.error}
        onRetry={() => projectQuery.refetch()}
      />
    )
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 p-4 lg:grid-cols-[280px_minmax(0,1fr)_320px]">
      <div className="space-y-4">
        <ProjectStats
          project={projectQuery.data}
          stats={statsQuery.data}
          isLoading={statsQuery.isLoading || projectQuery.isLoading}
        />
      </div>

      <div className="min-h-0">
        <EventStream projectId={projectId} />
      </div>

      <div className="min-h-0">
        <TodoList
          projectId={projectId}
          todos={todosQuery.data}
          isLoading={todosQuery.isLoading}
          error={todosQuery.error}
          onRetry={() => todosQuery.refetch()}
        />
      </div>
    </div>
  )
}

function AutoSelectFirst({
  firstId,
  onSelect,
}: {
  firstId: string | null
  onSelect: (id: string) => void
}) {
  useEffect(() => {
    if (firstId) onSelect(firstId)
  }, [firstId, onSelect])
  return <LoadingSkeleton variant="workbench" />
}
