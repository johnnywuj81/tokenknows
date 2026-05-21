#!/usr/bin/env node
/**
 * Playwright 自动截图机器人 · 跑过 demo-walkthrough 12 步, 输出 PNGs
 *
 * 用法:
 *   cd code/tokenknows-web
 *   node scripts/screenshot-bot.mjs <asset_id>
 *
 * 前置:
 *   - 后端 8001 + 前端 5173 已启
 *   - 已跑过 demo-seed.sh 拿到 asset_id (含 PII)
 *
 * 输出:
 *   engineering_handoff/demo-screenshots/NN-名称.png   (1280x800)
 */

import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdirSync } from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ASSET_ID = process.argv[2]
if (!ASSET_ID) {
  console.error('Usage: node scripts/screenshot-bot.mjs <asset_id>')
  process.exit(1)
}

const PROJECT = 'proj-demo-001'
const BASE = 'http://localhost:5173'
// 输出到 repo 根的 engineering_handoff/demo-screenshots/
const OUTPUT_DIR = path.resolve(__dirname, '..', '..', '..', 'engineering_handoff', 'demo-screenshots')
mkdirSync(OUTPUT_DIR, { recursive: true })

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled'],
  })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,                    // Retina
    locale: 'zh-CN',
    colorScheme: 'light',
  })
  const page = await context.newPage()
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.error('  page error:', msg.text().slice(0, 100))
  })

  async function snap(name, descripton) {
    const p = path.join(OUTPUT_DIR, `${name}.png`)
    await page.screenshot({ path: p, fullPage: false })
    console.log(`  ✓ ${name}.png · ${descripton}`)
  }

  async function waitText(text, timeout = 8000) {
    await page.waitForFunction(
      (t) => document.body.innerText.includes(t),
      text,
      { timeout },
    )
  }

  async function goto(url, waitFor) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 })
    // 等 MSW service worker + React 渲染
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    if (waitFor) {
      try {
        await waitText(waitFor, 15000)
      } catch (e) {
        console.warn(`  ⚠ goto: 等不到文字 "${waitFor}", 继续`)
      }
    }
    await page.waitForTimeout(1500) // 让动画完成
  }

  console.log('▸ 启动 Chromium · viewport 1280x800 @2x')
  console.log(`▸ asset_id: ${ASSET_ID}`)
  console.log(`▸ 输出: ${OUTPUT_DIR}`)

  // ── 00 登录 (MSW mock 接受任意密码, 走真表单触发持久化到 localStorage) ───
  console.log('▸ 00 登录...')
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.fill('input[type="email"]', 'demo@tokenknows.local')
  await page.fill('input[type="password"]', 'demo123')
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL(/projects/, { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(2000)

  // ── 01 工作台 ───────────────────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}`, '实时事件流')
  await snap('01-workbench', '工作台三栏 + 事件流')

  // ── 02 事件抽屉 (T04) ───────────────────────────────────────
  // 点 PR #127 卡片
  try {
    await page.getByText('PR #127').first().click({ timeout: 3000 })
    await waitText('事件详情')
    await page.waitForTimeout(500)
    await snap('02-event-drawer', 'T04 事件详情抽屉')
    await page.keyboard.press('Escape')
  } catch (e) {
    console.warn('  ⚠ 02 事件抽屉跳过:', e.message.slice(0, 60))
  }

  // ── 03 文档列表 ─────────────────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}/documents`, '项目文档')
  await snap('03-document-list', 'T05 文档列表')

  // ── 04 文档结果页 ───────────────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}/documents/${ASSET_ID}`, '本周进展')
  await page.waitForTimeout(1500) // TipTap 渲染 + 角标 hydrate
  await snap('04-document-page', 'T06 文档页 + LLM 内容 + [N] 角标')

  // ── 05 证据链抽屉 (T07) ─────────────────────────────────────
  try {
    // 点章节 1 footer 的 "查看证据"
    await page.getByRole('button', { name: '查看证据' }).first().click({ timeout: 3000 })
    await waitText('证据链')
    await page.waitForTimeout(800)
    await snap('05-evidence-drawer', 'T07 证据链抽屉 + tab')
    await page.keyboard.press('Escape')
  } catch (e) {
    console.warn('  ⚠ 05 证据抽屉跳过:', e.message.slice(0, 60))
  }

  // ── 06 重生成对话框 (T08) ───────────────────────────────────
  try {
    await page.getByRole('button', { name: '重生成' }).first().click({ timeout: 3000 })
    await waitText('重生成章节')
    await page.fill('#regen-instruction', '用更生动语气, 强调本周 EgressGate PR 和证据链抽屉')
    await page.waitForTimeout(300)
    await snap('06-regenerate-dialog', 'T08 重生成对话框 (已填指令)')
    await page.keyboard.press('Escape')
  } catch (e) {
    console.warn('  ⚠ 06 重生成 dialog 跳过:', e.message.slice(0, 60))
  }

  // ── 07 审批页 (T09) - 先提交审批 ────────────────────────────
  // 通过 API submit 强制 → 跳 review
  await page.evaluate(async ({ assetId }) => {
    await fetch(`/api/v1/assets/${assetId}/submit`, { method: 'POST' })
  }, { assetId: ASSET_ID })
  await goto(`${BASE}/projects/${PROJECT}/documents/${ASSET_ID}/review`, '章节审批')
  // 通过第 1 章
  try {
    await page.locator('aside button:has-text("通过")').first().click({ timeout: 3000 })
    await page.waitForTimeout(800)
  } catch (e) {
    console.warn('  ⚠ approve ch1 skipped')
  }
  await snap('07-review-page', 'T09 审批页 (§1 已通过)')

  // ── 08 脱敏页 (T10) ─────────────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}/documents/${ASSET_ID}/redaction`, '脱敏确认')
  await page.waitForTimeout(2000) // 自动 scan
  await snap('08-redaction-page', 'T10 脱敏页 4 项命中')

  // ── 09 发布对话框 (T11) ─────────────────────────────────────
  // 先把 asset 强制升 approved (绕过 approve all 5 chapters)
  await page.evaluate(async ({ assetId, project }) => {
    const chs = await (await fetch(`/api/v1/assets/${assetId}/chapters`)).json()
    for (const c of chs) {
      await fetch(`/api/v1/assets/${assetId}/chapters/${c.id}/approve`, { method: 'POST' })
    }
    void project
  }, { assetId: ASSET_ID, project: PROJECT })

  await goto(`${BASE}/projects/${PROJECT}/documents/${ASSET_ID}`, '周报')
  try {
    await page.getByRole('button', { name: /发布/ }).first().click({ timeout: 3000 })
    await waitText('发布文档')
    // 选公开链接
    await page.locator('input[value="public_link"]').check({ timeout: 2000 })
    // 勾确认
    await page.locator('input[type="checkbox"]').first().check()
    await page.waitForTimeout(500)
    await snap('09-publish-dialog', 'T11 发布对话框 (公开链接 + 已确认)')

    // 提交发布 → 跳回执
    await page.getByRole('button', { name: '确认发布' }).click({ timeout: 3000 })
    await page.waitForURL(/published/, { timeout: 8000 })
    await page.waitForTimeout(1500)
    await snap('10-publish-receipt', 'T12 发布回执 + diff')
  } catch (e) {
    console.warn('  ⚠ 09-10 发布跳过:', e.message.slice(0, 80))
  }

  // ── 11 设置 LLM 出域 (T14) ──────────────────────────────────
  await goto(`${BASE}/projects/${PROJECT}/settings?tab=llm`, '三层出域门禁')
  await snap('11-settings-llm', 'T14 LLM 出域 + provider 列表')

  // ── 12 Admin 控制台 (T15) ───────────────────────────────────
  await goto(`${BASE}/admin`, '实例管理')
  await snap('12-admin', 'T15 Admin 4 数字卡 + 容量')

  await browser.close()
  console.log('\n✓ 12 张截图完成. 下一步: ffmpeg 合成视频')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
