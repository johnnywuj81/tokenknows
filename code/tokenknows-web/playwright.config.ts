/**
 * Playwright 配置 · 视觉回归 + E2E.
 *
 * 跑测:
 *   npx playwright install --with-deps chromium
 *   npx playwright test
 *
 * 首次跑会创建 baseline 截图到 tests-e2e/visual.spec.ts-snapshots/.
 * 后续跑做像素 diff, 阈值 0.2% (避免字体渲染抖动 false-positive).
 *
 * webServer 会自动启 vite dev (端口 5173), 复用现有 MSW.
 */

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests-e2e',
  fullyParallel: false,                // 视觉回归串行避免 race
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'zh-CN',
    colorScheme: 'light',
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,              // CI 用 1x 减少 diff 噪音
  },

  expect: {
    // 视觉回归阈值: 0.2% 像素差异以内视为通过 (字体抗锯齿/光标闪烁等)
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      threshold: 0.2,
      animations: 'disabled',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
