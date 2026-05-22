/**
 * 视觉回归 · pure-frontend 屏幕 (无后端依赖, 仅 MSW + 静态路由).
 *
 * 首次跑创建 baseline:
 *   npx playwright test --update-snapshots
 *
 * 后续跑做 pixel diff (阈值 0.2% 配在 playwright.config.ts).
 *
 * 覆盖 5 屏 (依次为加载难度):
 *   1. /login           AuthLayout + LoginPage
 *   2. /register        AuthLayout + RegisterPage
 *   3. /forgot-password ForgotPasswordPage
 *   4. /                EmptyWorkbench (无项目 fallback)
 *   5. /projects/new    NewProjectPage step 1
 *
 * 不覆盖需要真后端的屏 (T05/T06/T07/T09/T10/T11/T12/T13/T14/T15)
 * 那些在 #1 E2E Playwright 用 walkthrough.spec.ts 单独覆盖.
 */

import { test, expect } from '@playwright/test'


test.describe('视觉回归 · 公开屏 (no auth needed)', () => {
  test('/login 登录页', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('欢迎回来')).toBeVisible()
    await expect(page).toHaveScreenshot('01-login.png', { fullPage: true })
  })

  test('/register 注册页', async ({ page }) => {
    await page.goto('/register')
    await page.waitForLoadState('networkidle')
    await expect(page.getByLabel('邮箱')).toBeVisible()
    await expect(page).toHaveScreenshot('02-register.png', { fullPage: true })
  })

  test('/forgot-password 忘记密码', async ({ page }) => {
    await page.goto('/forgot-password')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: '发送重置链接' })).toBeVisible()
    await expect(page).toHaveScreenshot('03-forgot-password.png', { fullPage: true })
  })

  test('/reset-password 重置密码', async ({ page }) => {
    await page.goto('/reset-password?token=test-token')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('重置密码')).toBeVisible()
    await expect(page).toHaveScreenshot('04-reset-password.png', { fullPage: true })
  })

  test('/verify-email 邮箱验证', async ({ page }) => {
    await page.goto('/verify-email?token=demo')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveScreenshot('05-verify-email.png', { fullPage: true })
  })
})


test.describe('视觉回归 · 业务屏 (auth via localStorage 注入)', () => {
  test.beforeEach(async ({ page }) => {
    // 注入已登录态: 写 localStorage 让 RequireAuth 通过
    // Key 必须匹配 src/stores/authStore.ts persist.name = 'tokenknows_auth'
    await page.goto('/login')
    await page.evaluate(() => {
      const authState = {
        state: {
          user: { id: 'u1', email: 'demo@tokenknows.local', display_name: 'Demo', role: 'editor', is_instance_admin: true },
          accessToken: 'tk-demo',
          refreshToken: 'rf-demo',
          isAuthenticated: true,
        },
        version: 0,
      }
      localStorage.setItem('tokenknows_auth', JSON.stringify(authState))
    })
  })

  test('/projects/new 新建项目向导 step 1', async ({ page }) => {
    await page.goto('/projects/new')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: '建立你的研发知识空间' })).toBeVisible()
    await expect(page).toHaveScreenshot('06-new-project.png', { fullPage: true })
  })

  test('/ EmptyWorkbench (无项目时)', async ({ page }) => {
    // 让 /projects 返回空列表 (默认 MSW handler 可能已有 fixture, 不强求)
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500) // MSW + React Query 加载
    await expect(page).toHaveScreenshot('07-workbench-or-empty.png', { fullPage: true })
  })
})
