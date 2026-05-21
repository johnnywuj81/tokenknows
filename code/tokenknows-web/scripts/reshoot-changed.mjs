#!/usr/bin/env node
/**
 * 只重拍 3 张因近期 UI 改动而过时的截图:
 *   01-workbench       · 加了 DatasourcesCard (左栏 5 源表)
 *   03-document-list   · 加了 "相似" 第 4 列
 *   09-publish-dialog  · 加了 similarity > 0.85 警告横幅
 *
 * 用法: cd code/tokenknows-web && node scripts/reshoot-changed.mjs <asset_id>
 *
 * 前置:
 *   - 后端 8001 + 前端 5173 已启
 *   - asset_id 的 metrics.similarity > 0.85 (这次用 asset-9f2a5d0603 = 0.999)
 *   - asset 的 status='draft' 或 'approved' (能进 PublishDialog)
 */

import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdirSync } from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ASSET_ID = process.argv[2] || 'asset-9f2a5d0603'

const PROJECT = 'proj-demo-001'
const BASE = 'http://localhost:5173'
const OUTPUT_DIR = path.resolve(
  __dirname, '..', '..', '..', 'engineering_handoff', 'demo-screenshots',
)
mkdirSync(OUTPUT_DIR, { recursive: true })

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled'],
  })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    locale: 'zh-CN',
    colorScheme: 'light',
  })
  const page = await context.newPage()

  async function snap(name, desc) {
    const p = path.join(OUTPUT_DIR, `${name}.png`)
    await page.screenshot({ path: p, fullPage: false })
    console.log(`  ✓ ${name}.png · ${desc}`)
  }

  async function waitText(text, timeout = 12000) {
    await page.waitForFunction(
      (t) => document.body.innerText.includes(t),
      text,
      { timeout },
    )
  }

  async function goto(url, waitFor) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 })
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    if (waitFor) {
      try { await waitText(waitFor, 15000) } catch (e) {}
    }
    await page.waitForTimeout(1500)
  }

  console.log('▸ 登录')
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.fill('input[type="email"]', 'demo@tokenknows.local')
  await page.fill('input[type="password"]', 'demo123')
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL(/projects/, { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(2500)

  // ── 01 工作台 (加 DatasourcesCard) ─────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}`, '数据源')   // 等 DatasourcesCard 出现
  await page.waitForTimeout(2000)  // 5 源 query 完成
  await snap('01-workbench', '工作台 + 新 DatasourcesCard 5 源')

  // ── 03 文档列表 (加相似列) ─────────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}/documents`, '项目文档')
  await page.waitForTimeout(1500)
  await snap('03-document-list', '文档列表 · 新增 "相似" 第 4 列')

  // ── 09 发布对话框 (similarity > 0.85 警告) ─────────────────────
  // 前置: 把 asset 推进到 approved (DocHeader 的"发布" 按钮 gates 在 canPublish)
  await page.evaluate(async ({ assetId }) => {
    // 先 submit (draft → in_review)
    await fetch(`/api/v1/assets/${assetId}/submit`, { method: 'POST' }).catch(() => {})
    // 再 approve 全部 chapter (in_review → approved)
    const chs = await (await fetch(`/api/v1/assets/${assetId}/chapters`)).json()
    for (const c of chs) {
      await fetch(`/api/v1/assets/${assetId}/chapters/${c.id}/approve`, { method: 'POST' })
    }
  }, { assetId: ASSET_ID })

  await goto(`${BASE}/projects/${PROJECT}/documents/${ASSET_ID}`, '周报')
  try {
    await page.getByRole('button', { name: /发布/ }).first().click({ timeout: 5000 })
    await waitText('发布文档', 8000)
    // 勾确认 checkbox
    await page.locator('input[type="checkbox"]').first().check({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(800)
    await snap('09-publish-dialog', 'T11 发布对话框 · 含 similarity 警告')
  } catch (e) {
    console.warn('  ⚠ 09 跳过:', e.message.slice(0, 80))
  }

  await browser.close()
  console.log('\n✓ 3 张截图刷新完成')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
