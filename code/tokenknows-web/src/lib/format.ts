/**
 * Format helpers · 跨 feature 共享 (避免重复实现).
 *
 * 此前 formatRelative 在 4 处重复:
 *   DatasourcesCard / DocumentCard / ProjectStats / AdminUsersPage
 * 统一到此文件 + 单测覆盖阈值.
 */

/**
 * ISO 8601 时间戳 → 相对中文表达, 例如 "3 分钟前" / "2 天前" / "5 个月前".
 *
 * - <60s         刚刚
 * - <60min       N 分钟前
 * - <24h         N 小时前
 * - <30d         N 天前
 * - <365d        N 个月前
 * - >=365d       N 年前
 *
 * 输入: ISO 8601 string (含 Z 或 +HH:MM 时区).
 * 注: 不接收 Date 对象, 保持调用点习惯一致 (后端返 ISO string).
 */
export function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`
  if (diff < 86400 * 365) return `${Math.floor(diff / (86400 * 30))} 个月前`
  return `${Math.floor(diff / (86400 * 365))} 年前`
}
