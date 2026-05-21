/**
 * formatRelative 单测 · 阈值边界 + 输出格式.
 *
 * 用 vi.useFakeTimers 固定"现在", 测各档输出.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { formatRelative } from './format'

const FIXED_NOW = new Date('2026-05-22T12:00:00Z').getTime()

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(FIXED_NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

function isoAgo(seconds: number): string {
  return new Date(FIXED_NOW - seconds * 1000).toISOString()
}

describe('formatRelative', () => {
  it('returns "刚刚" within 60s', () => {
    expect(formatRelative(isoAgo(0))).toBe('刚刚')
    expect(formatRelative(isoAgo(30))).toBe('刚刚')
    expect(formatRelative(isoAgo(59))).toBe('刚刚')
  })

  it('crosses to "分钟前" at 60s', () => {
    expect(formatRelative(isoAgo(60))).toBe('1 分钟前')
    expect(formatRelative(isoAgo(150))).toBe('2 分钟前')
    expect(formatRelative(isoAgo(3599))).toBe('59 分钟前')
  })

  it('crosses to "小时前" at 3600s', () => {
    expect(formatRelative(isoAgo(3600))).toBe('1 小时前')
    expect(formatRelative(isoAgo(7200))).toBe('2 小时前')
    expect(formatRelative(isoAgo(86399))).toBe('23 小时前')
  })

  it('crosses to "天前" at 86400s (24h)', () => {
    expect(formatRelative(isoAgo(86400))).toBe('1 天前')
    expect(formatRelative(isoAgo(86400 * 7))).toBe('7 天前')
    expect(formatRelative(isoAgo(86400 * 29))).toBe('29 天前')
  })

  it('crosses to "个月前" at 30d', () => {
    expect(formatRelative(isoAgo(86400 * 30))).toBe('1 个月前')
    expect(formatRelative(isoAgo(86400 * 60))).toBe('2 个月前')
    expect(formatRelative(isoAgo(86400 * 364))).toBe('12 个月前')
  })

  it('crosses to "年前" at 365d', () => {
    expect(formatRelative(isoAgo(86400 * 365))).toBe('1 年前')
    expect(formatRelative(isoAgo(86400 * 730))).toBe('2 年前')
  })

  it('handles ISO with Z suffix', () => {
    expect(formatRelative(isoAgo(120))).toBe('2 分钟前')
  })
})
