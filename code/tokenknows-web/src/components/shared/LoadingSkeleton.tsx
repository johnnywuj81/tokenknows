/**
 * LoadingSkeleton · 整屏骨架组合。
 *
 * 设计依据: SharedFoundations.md §3.4
 *
 * 与 shadcn/Skeleton 的边界:
 *   - shadcn/Skeleton 是原子(单个灰色矩形)
 *   - LoadingSkeleton 是组合(整屏占位结构)
 *
 * 用法:
 *   {isLoading ? <LoadingSkeleton variant="workbench" /> : <WorkbenchContent ... />}
 */

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type LoadingSkeletonVariant =
  | 'workbench'   // T03 三栏
  | 'list'        // T05 / T15 卡片网格
  | 'document'    // T06 / T09 文档大纲 + 章节
  | 'form'        // T01 / T02 / T13 / T14 表单
  | 'drawer'      // T04 / T07 抽屉
  | 'card'        // 通用单卡内文字行

interface LoadingSkeletonProps {
  variant: LoadingSkeletonVariant
  className?: string
}

export function LoadingSkeleton({ variant, className }: LoadingSkeletonProps) {
  return (
    <div className={cn('animate-in fade-in', className)} aria-busy="true" aria-live="polite">
      {variant === 'workbench' && <WorkbenchSkeleton />}
      {variant === 'list' && <ListSkeleton />}
      {variant === 'document' && <DocumentSkeleton />}
      {variant === 'form' && <FormSkeleton />}
      {variant === 'drawer' && <DrawerSkeleton />}
      {variant === 'card' && <CardSkeleton />}
    </div>
  )
}

function WorkbenchSkeleton() {
  return (
    <div className="grid h-full grid-cols-[240px_1fr_320px] gap-6 p-6">
      {/* 左侧栏:项目卡 */}
      <div className="space-y-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
      {/* 中间:事件流 */}
      <div className="space-y-3">
        <Skeleton className="h-8 w-1/3" />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
      {/* 右侧:待办 */}
      <div className="space-y-3">
        <Skeleton className="h-8 w-1/2" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  )
}

function ListSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="space-y-3 rounded-lg border border-border-subtle p-4">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-20 w-full" />
          <div className="flex items-center gap-2">
            <Skeleton className="size-6 rounded-full" />
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
      ))}
    </div>
  )
}

function DocumentSkeleton() {
  return (
    <div className="grid h-full grid-cols-[240px_1fr_320px] gap-6 p-6">
      {/* 左:大纲 */}
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
      {/* 中:章节 */}
      <div className="space-y-6">
        <Skeleton className="h-10 w-2/3" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        ))}
      </div>
      {/* 右:侧栏 */}
      <div className="space-y-3">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  )
}

function FormSkeleton() {
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-10 w-full" />
        </div>
      ))}
      <Skeleton className="mt-4 h-10 w-full" />
    </div>
  )
}

function DrawerSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-4 w-1/3" />
      <div className="space-y-3 pt-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="space-y-2 p-4">
      <Skeleton className="h-5 w-1/2" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  )
}
