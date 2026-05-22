/**
 * DocOutline · 左侧章节大纲 + 锚点滚动联动
 *
 * 设计依据 任务包 T06 §8:
 *   - 大纲点击 → 平滑滚动 + 当前章节高亮
 *   - 章节滚动到中间区域时, 左侧大纲对应项高亮 (IntersectionObserver)
 *   - 长文档 (> 20 章) 左侧大纲有自己的 ScrollArea
 *
 * v0.2 · 自动检测 book 类型 (任一 chapter.depth > 0 或有 parent_id),
 *        渲染嵌套 卷 → 章 结构,每卷可折叠.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, Hash } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Chapter } from '@/types/api'

interface DocOutlineProps {
  chapters: Chapter[]
  // 滚动容器 (中间正文区域)
  scrollRef: React.RefObject<HTMLElement | null>
}

/** v0.2 · 检测是否是 book 类型 (任一 chapter.depth > 0 或有 parent_id). */
function isBookOutline(chapters: Chapter[]): boolean {
  return chapters.some((c) => (c.depth ?? 0) > 0 || c.parent_id != null)
}

interface VolumeGroup {
  volume: Chapter
  chapters: Chapter[]
}

/** v0.2 · 把 flat chapters 按 parent_id 重组成嵌套结构. */
function groupByVolume(chapters: Chapter[]): VolumeGroup[] {
  const volumes = chapters.filter((c) => (c.depth ?? 0) === 0)
  return volumes.map((vol) => ({
    volume: vol,
    chapters: chapters.filter((c) => c.parent_id === vol.id),
  }))
}

export function DocOutline({ chapters, scrollRef }: DocOutlineProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)
  const isBook = useMemo(() => isBookOutline(chapters), [chapters])

  // 监听章节标题进入视口 → 高亮对应大纲项
  useEffect(() => {
    if (!chapters.length) return
    // 等下一帧让 ChapterBlock 已挂载
    const id = requestAnimationFrame(() => {
      const root = scrollRef.current
      if (!root) return
      observerRef.current?.disconnect()
      observerRef.current = new IntersectionObserver(
        (entries) => {
          // 取 viewport 上 1/3 的可见章节作为 active
          const visible = entries.filter((e) => e.isIntersecting)
          if (visible.length > 0) {
            visible.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
            const top = visible[0]?.target.id
            if (top) setActiveId(top.replace('chapter-anchor-', ''))
          }
        },
        {
          root,
          rootMargin: '-10% 0px -60% 0px',
          threshold: 0,
        },
      )
      for (const ch of chapters) {
        const el = document.getElementById(`chapter-anchor-${ch.id}`)
        if (el) observerRef.current.observe(el)
      }
    })
    return () => {
      cancelAnimationFrame(id)
      observerRef.current?.disconnect()
    }
  }, [chapters, scrollRef])

  const handleClick = (chapterId: string) => {
    const el = document.getElementById(`chapter-anchor-${chapterId}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setActiveId(chapterId)
  }

  if (isBook) {
    return (
      <BookOutlineNav
        chapters={chapters}
        activeId={activeId}
        onClick={handleClick}
      />
    )
  }

  return (
    <nav
      className="flex h-full flex-col gap-1 overflow-auto border-r border-border-subtle bg-bg-card px-3 py-4"
      aria-label="文档大纲"
    >
      <p className="px-2 pb-2 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
        大纲 · {chapters.length} 章
      </p>
      <ol className="space-y-0.5">
        {chapters.map((ch) => {
          const active = ch.id === activeId
          return (
            <li key={ch.id}>
              <button
                type="button"
                onClick={() => handleClick(ch.id)}
                className={cn(
                  'flex w-full items-start gap-1.5 rounded-md px-2 py-1.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary',
                  active
                    ? 'bg-accent-primary-light text-accent-primary-dark'
                    : 'text-text-secondary hover:bg-bg-warm',
                )}
              >
                <Hash className="size-3 mt-1 shrink-0 text-text-subtle" />
                <span className="flex-1 font-ui text-body-sm">
                  {ch.order_index + 1}. {ch.title}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

interface BookOutlineNavProps {
  chapters: Chapter[]
  activeId: string | null
  onClick: (id: string) => void
}

function BookOutlineNav({ chapters, activeId, onClick }: BookOutlineNavProps) {
  const groups = useMemo(() => groupByVolume(chapters), [chapters])
  // 卷折叠状态; 默认全展开
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const toggle = (volId: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(volId)) next.delete(volId)
      else next.add(volId)
      return next
    })

  return (
    <nav
      className="flex h-full flex-col gap-1 overflow-auto border-r border-border-subtle bg-bg-card px-3 py-4"
      aria-label="书籍大纲"
    >
      <p className="px-2 pb-2 font-ui text-eyebrow uppercase tracking-wider text-text-muted">
        书籍大纲 · {groups.length} 卷 · {chapters.length - groups.length} 章
      </p>
      <ol className="space-y-1">
        {groups.map((group) => {
          const isCollapsed = collapsed.has(group.volume.id)
          const volActive = group.volume.id === activeId
          return (
            <li key={group.volume.id}>
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => toggle(group.volume.id)}
                  className="rounded p-0.5 text-text-subtle hover:bg-bg-warm"
                  aria-label={isCollapsed ? '展开本卷' : '折叠本卷'}
                  aria-expanded={!isCollapsed}
                >
                  <ChevronRight
                    className={cn(
                      'size-3 transition-transform',
                      !isCollapsed && 'rotate-90',
                    )}
                  />
                </button>
                <button
                  type="button"
                  onClick={() => onClick(group.volume.id)}
                  className={cn(
                    'flex flex-1 items-baseline gap-1.5 rounded-md px-2 py-1 text-left font-content font-semibold transition',
                    volActive
                      ? 'bg-accent-primary-light text-accent-primary-dark'
                      : 'text-text-primary hover:bg-bg-warm',
                  )}
                >
                  <span className="font-ui text-body-sm">{group.volume.title}</span>
                </button>
              </div>
              {!isCollapsed && group.chapters.length > 0 && (
                <ol className="ml-5 space-y-0.5 border-l border-border-subtle pl-2">
                  {group.chapters.map((ch) => {
                    const active = ch.id === activeId
                    return (
                      <li key={ch.id}>
                        <button
                          type="button"
                          onClick={() => onClick(ch.id)}
                          className={cn(
                            'flex w-full items-start gap-1.5 rounded-md px-2 py-1 text-left transition',
                            active
                              ? 'bg-accent-primary-light text-accent-primary-dark'
                              : 'text-text-secondary hover:bg-bg-warm',
                          )}
                        >
                          <Hash className="size-3 mt-1 shrink-0 text-text-subtle" />
                          <span className="flex-1 font-ui text-body-sm">
                            {ch.title}
                          </span>
                        </button>
                      </li>
                    )
                  })}
                </ol>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
