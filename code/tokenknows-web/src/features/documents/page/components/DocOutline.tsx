/**
 * DocOutline · 左侧章节大纲 + 锚点滚动联动
 *
 * 设计依据 任务包 T06 §8:
 *   - 大纲点击 → 平滑滚动 + 当前章节高亮
 *   - 章节滚动到中间区域时, 左侧大纲对应项高亮 (IntersectionObserver)
 *   - 长文档 (> 20 章) 左侧大纲有自己的 ScrollArea
 */

import { useEffect, useRef, useState } from 'react'
import { Hash } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Chapter } from '@/types/api'

interface DocOutlineProps {
  chapters: Chapter[]
  // 滚动容器 (中间正文区域)
  scrollRef: React.RefObject<HTMLElement | null>
}

export function DocOutline({ chapters, scrollRef }: DocOutlineProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)

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
