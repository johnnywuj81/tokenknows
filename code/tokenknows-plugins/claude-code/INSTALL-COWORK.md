# tokenknows · Claude Cowork 安装

本 plugin **同时兼容 Claude Cowork** (与 Claude Code 同结构: 同样的 `plugin.json`/`skills/`/`commands/`/`.mcp.json`)。无需任何代码改动。

## 安装方式

### 方式 1 · GitHub 自托管 marketplace (推荐)

在 Claude Cowork 内:
1. 设置 → Plugins → "Add marketplace from GitHub"
2. 输入: `johnnywuj81/tokenknows` (path: `code/tokenknows-plugins/claude-code`)
3. Install `tokenknows`

或在 macOS terminal:

```bash
# Cowork CLI (与 Code CLI 共用)
claude plugin marketplace add johnnywuj81/tokenknows
claude plugin install tokenknows
```

### 方式 2 · zip 上传 (离线/内网)

```bash
cd code/tokenknows-plugins
zip -r tokenknows-plugin.zip claude-code
# 上传 tokenknows-plugin.zip 到 claude.com/plugins
```

## 环境变量

Cowork plugin 与 Code 一样,**必须先 export 4 个变量到 host shell**:

```bash
# macOS: 写到 ~/.zshrc 让 Cowork 启动时能读到
export TOKENKNOWS_API_ROOT="/abs/path/to/tokenknows/code/tokenknows-api"
export TOKENKNOWS_API_BASE="http://127.0.0.1:8001"
export TOKENKNOWS_DEFAULT_PROJECT="proj-demo-001"
export TOKENKNOWS_API_TOKEN=""
```

**重要**: Cowork (桌面 app) 启动时只继承 GUI launch 时的 env (一般是 `~/.zshenv` / launchd `setenv`),不读 `~/.zshrc`。建议:

```bash
# macOS · launchctl setenv (永久, 重启后仍生效)
launchctl setenv TOKENKNOWS_API_ROOT "/abs/path/to/tokenknows/code/tokenknows-api"
launchctl setenv TOKENKNOWS_API_BASE "http://127.0.0.1:8001"
launchctl setenv TOKENKNOWS_DEFAULT_PROJECT "proj-demo-001"
```

或者在 macOS Login Items 跑一个脚本设这些 env。

## Cowork vs Code 行为差异

| 维度 | Claude Cowork | Claude Code |
|---|---|---|
| 触发 skill 主要方式 | 用户自然语言描述意图 | 用户敲 `/tokenknows:weekly` |
| Slash command 命名 | `/tokenknows:weekly` (同) | `/tokenknows:weekly` (同) |
| hook 支持 | Cowork 当前不支持 hooks | Code 支持 PreToolUse/PostToolUse/Stop |
| 多 session 状态 | Cowork 单 conversation 内 | Code 跨 session (T118 daemon 监 `~/.claude/projects/*.jsonl`) |
| 适合场景 | 商务对话 → ADR/PRD/方案 | 编程对话 → 周报/复盘/KG |

## 验证

启 Cowork → 进任意对话:

```
你: "帮我整理一下这次讨论的架构决策"
   ↓
Cowork 自动用 tokenknows:distill skill →
  · submit_session_events
  · distill_document(type="adr")
  · get_asset_chapters
   ↓
返回 5 段 ADR markdown
```

如果 skill 没自动触发,显式说 `/tokenknows:adr`。

## 排错

- **slash command 不出现**: 重启 Cowork; 确认 plugin 在 Plugins 设置里 enabled
- **MCP server 启动失败**: 检查 `launchctl getenv TOKENKNOWS_API_ROOT` 是否返回正确路径; Cowork 不读 `~/.zshrc`
- **backend 网络不通**: macOS firewall 检查 `127.0.0.1:8001` 是否被拦
