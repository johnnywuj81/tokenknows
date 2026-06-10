#!/usr/bin/env node
/**
 * 一次性生成 TokenKnows wordmark 的文字轮廓 path.
 *
 * 为什么 text-to-path:
 *   - 本机/CI 不一定装 Poppins;
 *   - GitHub 的 SVG CSP 会拦 webfont — 带 <text> 的 SVG 在 GitHub 上
 *     会退化为系统 sans, 字形漂移。
 *   轮廓化后任何环境渲染一致。
 *
 * 字体: Poppins SemiBold (OFL 1.1 — 轮廓嵌入 logo 明确允许)
 *   来源: https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf
 *
 * 用法:
 *   curl -sL -o /tmp/Poppins-SemiBold.ttf <上面的 URL>
 *   npx --yes --package=text-to-svg node scripts/brand/build-wordmark.mjs /tmp/Poppins-SemiBold.ttf
 * 输出: stdout 打印 path d= 字符串 + 度量, 手工拼进 tokenknows-wordmark*.svg
 */

import TextToSVG from 'text-to-svg'

const fontPath = process.argv[2]
if (!fontPath) {
  console.error('usage: node build-wordmark.mjs <Poppins-SemiBold.ttf>')
  process.exit(1)
}

const t2s = TextToSVG.loadSync(fontPath)
const text = 'TokenKnows'
const fontSize = 96

const metrics = t2s.getMetrics(text, { fontSize })
const d = t2s.getD(text, { fontSize, x: 0, y: 0, anchor: 'left baseline' })

console.log(JSON.stringify({ metrics }, null, 2))
console.log('--- path d ---')
console.log(d)
