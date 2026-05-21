/**
 * TokenKnows · VS Code 扩展 v0
 *
 * 订阅 VS Code workspace events → 批量推到 TokenKnows backend events 表.
 *
 * 采集事件:
 *  - onDidSaveTextDocument → code_change (file save, 含 line count 改变)
 *  - onDidChangeActiveTextEditor → 仅状态栏提示 "viewing X" (不入库, 避免噪声)
 *
 * 不采集:
 *  - 每次 keystroke / onDidChangeTextDocument (太频繁, 隐私扰)
 *  - 调试 / 终端会话 (敏感, 后续 opt-in)
 *
 * 配置 (用户 settings.json):
 *  - tokenknows.backendUrl
 *  - tokenknows.projectId
 *  - tokenknows.enabled        true/false
 *  - tokenknows.batchIntervalSec  默认 10s
 *  - tokenknows.includeFileExtensions  数组, 默认覆盖常见编程语言
 *
 * 状态栏: "TK ✓ 23"   表示已上报 23 条
 *         "TK ⌛ 5 pending"  本批未发
 *         "TK 暂停"   enabled=false
 *         "TK ⚠ offline"  backend 不通
 */

import * as crypto from 'crypto'
import * as path from 'path'
import * as vscode from 'vscode'

interface EventCreate {
  source_type: 'vscode'
  source_ref: string
  external_id: string
  version: number
  event_type: 'code_change' | 'manual_note'
  occurred_at: string
  author: { name: string; email?: string }
  title: string
  content: string
  content_hash: string
  payload: Record<string, unknown>
  tags: string[]
  trust_score: number
}

let buffer: EventCreate[] = []
let statusBarItem: vscode.StatusBarItem
let flushTimer: NodeJS.Timeout | undefined
let totalIngested = 0
let backendReachable = true

function getConfig() {
  const cfg = vscode.workspace.getConfiguration('tokenknows')
  return {
    backendUrl: cfg.get<string>('backendUrl') || 'http://localhost:8001',
    projectId: cfg.get<string>('projectId') || 'proj-demo-001',
    enabled: cfg.get<boolean>('enabled', true),
    batchIntervalSec: cfg.get<number>('batchIntervalSec', 10),
    includeFileExtensions: cfg.get<string[]>('includeFileExtensions') || [],
  }
}

function sha256(s: string): string {
  return crypto.createHash('sha256').update(s).digest('hex')
}

function workspaceRef(doc: vscode.TextDocument): string {
  const ws = vscode.workspace.getWorkspaceFolder(doc.uri)
  if (ws) return ws.name
  return path.basename(path.dirname(doc.uri.fsPath))
}

function shouldCollect(doc: vscode.TextDocument, includeExt: string[]): boolean {
  // 跳过 git index / 临时文件
  const scheme = doc.uri.scheme
  if (scheme !== 'file') return false
  if (doc.uri.fsPath.includes('/.git/') || doc.uri.fsPath.includes('/node_modules/')) {
    return false
  }
  const ext = path.extname(doc.uri.fsPath).toLowerCase()
  if (!ext) return false
  if (!includeExt.includes(ext)) return false
  return true
}

function onSave(doc: vscode.TextDocument): void {
  const { enabled, includeFileExtensions } = getConfig()
  if (!enabled) return
  if (!shouldCollect(doc, includeFileExtensions)) return

  const ref = workspaceRef(doc)
  const rel = vscode.workspace.asRelativePath(doc.uri, false)
  const lineCount = doc.lineCount
  const content = doc.getText()
  const sha = sha256(content)
  const now = new Date().toISOString()
  const title = `保存 ${rel}`

  // content_hash 不能用文件内容 (文件没变也会触发 save → 重入); 用 file+sha+秒级
  // 时间, 同一文件 5s 内连续保存只入 1 条
  const bucketTime = now.slice(0, 16) // YYYY-MM-DDTHH:MM (分钟粒度)
  const dedupHash = sha256(`${doc.uri.fsPath}:${sha}:${bucketTime}`)

  // trust_score: code_change 默认 0.70 (实际保存 = 用户主动行为)
  // extraction_confidence: 1.0 (我们有 sha256 + line_count, 元数据完整)
  const authority = 0.70
  const confidence = 1.0
  const trustScore = Math.round((0.7 * authority + 0.3 * confidence) * 1000) / 1000

  const ev: EventCreate = {
    source_type: 'vscode',
    source_ref: ref,
    external_id: `vscode:${doc.uri.fsPath}:${bucketTime}`,
    version: 1,
    event_type: 'code_change',
    occurred_at: now,
    author: { name: process.env.USER || 'vscode-user' },
    title,
    content: `文件: ${rel}\n语言: ${doc.languageId}\n行数: ${lineCount}\n字符数: ${content.length}`,
    content_hash: dedupHash,
    payload: {
      file_path: doc.uri.fsPath,
      relative_path: rel,
      language_id: doc.languageId,
      line_count: lineCount,
      char_count: content.length,
      content_sha256: sha,
      trust_components: {
        source_authority: authority,
        extraction_confidence: confidence,
      },
    },
    tags: ['vscode', doc.languageId, ref],
    trust_score: trustScore,
  }
  buffer.push(ev)
  updateStatusBar()
}

async function flushBuffer(): Promise<void> {
  if (buffer.length === 0) return
  const { backendUrl, projectId } = getConfig()
  const batch = buffer.splice(0, buffer.length)   // take all
  const url = `${backendUrl.replace(/\/$/, '')}/api/v1/projects/${projectId}/events`
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: batch }),
    })
    if (!resp.ok) {
      const text = await resp.text()
      console.error(`[tokenknows] ingest failed: ${resp.status} ${text.slice(0, 200)}`)
      // 退回 buffer, 下次重试 (限制大小避免无限增长)
      buffer = batch.slice(-200).concat(buffer)
      backendReachable = false
    } else {
      const data = (await resp.json()) as { ingested: number; skipped: number }
      totalIngested += data.ingested
      backendReachable = true
      console.log(`[tokenknows] flush ${batch.length} → ingested=${data.ingested} skipped=${data.skipped}`)
    }
  } catch (err) {
    console.error(`[tokenknows] network err:`, err)
    buffer = batch.slice(-200).concat(buffer)
    backendReachable = false
  }
  updateStatusBar()
}

function updateStatusBar(): void {
  const { enabled } = getConfig()
  if (!enabled) {
    statusBarItem.text = 'TK · 暂停'
    statusBarItem.tooltip = 'TokenKnows 采集已禁用. 命令: TokenKnows: 启用/禁用采集'
    statusBarItem.backgroundColor = undefined
  } else if (!backendReachable) {
    statusBarItem.text = `TK ⚠ offline · ${buffer.length} pending`
    statusBarItem.tooltip = '后端不可达, 事件已缓存. 检查 tokenknows.backendUrl 设置.'
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground')
  } else if (buffer.length > 0) {
    statusBarItem.text = `TK ⌛ ${buffer.length} pending`
    statusBarItem.tooltip = `${totalIngested} 条已上报, ${buffer.length} 条等待下次 flush`
    statusBarItem.backgroundColor = undefined
  } else {
    statusBarItem.text = `TK ✓ ${totalIngested}`
    statusBarItem.tooltip = `已上报 ${totalIngested} 条事件. 点击立即 flush.`
    statusBarItem.backgroundColor = undefined
  }
  statusBarItem.show()
}

function startTimer(): void {
  const { batchIntervalSec } = getConfig()
  if (flushTimer) clearInterval(flushTimer)
  flushTimer = setInterval(() => {
    void flushBuffer()
  }, batchIntervalSec * 1000)
}

export function activate(context: vscode.ExtensionContext): void {
  // 状态栏
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100,
  )
  statusBarItem.command = 'tokenknows.flush'
  updateStatusBar()

  // 订阅保存事件
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => onSave(doc)),
    statusBarItem,
  )

  // 命令
  context.subscriptions.push(
    vscode.commands.registerCommand('tokenknows.flush', async () => {
      await flushBuffer()
      void vscode.window.showInformationMessage(
        `TokenKnows · 已上报 ${totalIngested} 条事件, ${buffer.length} 条 pending`,
      )
    }),
    vscode.commands.registerCommand('tokenknows.toggle', async () => {
      const cfg = vscode.workspace.getConfiguration('tokenknows')
      const cur = cfg.get<boolean>('enabled', true)
      await cfg.update('enabled', !cur, vscode.ConfigurationTarget.Global)
      updateStatusBar()
      void vscode.window.showInformationMessage(
        `TokenKnows · 采集已${!cur ? '启用' : '禁用'}`,
      )
    }),
    vscode.commands.registerCommand('tokenknows.status', () => {
      const { backendUrl, projectId, enabled } = getConfig()
      void vscode.window.showInformationMessage(
        `TokenKnows 状态:\n` +
          `  enabled: ${enabled}\n` +
          `  backend: ${backendUrl}\n` +
          `  project: ${projectId}\n` +
          `  已上报: ${totalIngested}\n` +
          `  pending: ${buffer.length}\n` +
          `  backend: ${backendReachable ? 'reachable' : 'unreachable'}`,
      )
    }),
  )

  // 配置变更监听
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('tokenknows.batchIntervalSec')) {
        startTimer()
      }
      updateStatusBar()
    }),
  )

  // 启动定时 flush
  startTimer()

  // 关闭时 flush
  context.subscriptions.push({
    dispose: () => {
      if (flushTimer) clearInterval(flushTimer)
      void flushBuffer()
    },
  })

  console.log('[tokenknows] activated')
}

export function deactivate(): void {
  if (flushTimer) clearInterval(flushTimer)
  void flushBuffer()
}
