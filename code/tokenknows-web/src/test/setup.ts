/**
 * Vitest setup · jest-dom matchers + 全局 DOM cleanup.
 *
 * 自动跑在每个 test 文件前 (vitest.config.ts setupFiles).
 */

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个 test 后清理 DOM, 防止跨文件污染
afterEach(() => {
  cleanup()
})
