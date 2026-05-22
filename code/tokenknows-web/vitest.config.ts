/// <reference types="vitest" />
/**
 * Vitest 配置 · 单元测试.
 *
 * 复用 vite.config.ts 里的 plugins + alias, 加 test 块即可.
 * 用 jsdom 跑 React Testing Library; happy-dom 也可但 jsdom 更稳.
 *
 * 跑测:  npm test
 * 覆盖率: npm test -- --coverage
 */

import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      exclude: ['node_modules', 'dist', '.git', 'tests-playwright/**'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        include: ['src/**'],
        exclude: [
          'node_modules/**',
          'dist/**',
          'src/main.tsx',
          'src/mocks/**',
          'src/test/**',
          '**/*.test.{ts,tsx}',
          '**/*.d.ts',
          'src/types/**',
          // shadcn/ui primitives: 第三方组件原文, 通过业务组件使用
          'src/components/ui/**',
        ],
      },
    },
  }),
)
