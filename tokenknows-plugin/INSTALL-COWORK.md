# tokenknows · Claude Cowork 安装

本 plugin **同时兼容 Claude Cowork** (与 Claude Code 同结构: 同样的 `plugin.json`/`skills/`/`commands/`/`.mcp.json`)。无需任何代码改动。

## 前置

与 Claude Code 相同 (详见 [README.md](./README.md) "5 分钟跑通"):

1. **backend** 跑在 `http://127.0.0.1:8001`
2. **Web 工作台** 跑在 `http://localhost:5173` — 注册/登录后在 **项目设置 → MCP 接入** 自助创建 API token (公网/开鉴权部署时需要)
3. **uv** 已安装 — MCP server 经 `uvx` 从 PyPI 拉起 (`tokenknows-mcp`),不需要 clone 仓库

> ⚠️ **Cowork 专属 uvx PATH 注意**: GUI 启动的 app 不继承 `~/.zshrc` 的 PATH,
> `~/.local/bin`(uv 默认安装位置)可能不在 Cowork 的 PATH 里。验证:
> `launchctl getenv PATH`。如果 uvx 找不到,两个办法:
> `launchctl setenv PATH "$HOME/.local/bin:$(launchctl getenv PATH)"`,
> 或 `brew install uv` (Homebrew 路径通常在 GUI PATH 里)。

## 安装方式

### 方式 1 · GitHub 自托管 marketplace (推荐)

在 Claude Cowork 内:
1. 设置 → Plugins → "Add marketplace from GitHub"
2. 输入: `johnnywuj81/tokenknows` (**只 owner/repo, 不要带子路径**)
3. Sync → 然后从列表选 `tokenknows` 装

> ⚠️ Cowork 严格在 repo root 找 `.claude-plugin/marketplace.json`,本仓库
> 已经在 root 放好,plugin 实际位于 `tokenknows-plugin/` 由 marketplace manifest
> 的 source 字段指向,Cowork 会自动处理。
>
> 历史教训: 早期 source 路径是 `./code/tokenknows-plugins/claude-code` (3 层),
> Cowork sandbox sync 实测拉不到子目录文件 → plugin 看似装好但 .mcp.json
> 没到本地, MCP server 永远启动不了. 改成 root 浅层路径后修复.

或在 macOS terminal:

```bash
# Cowork CLI (与 Code CLI 共用)
claude plugin marketplace add johnnywuj81/tokenknows
claude plugin install tokenknows
```

### 方式 2 · zip 上传 (离线/内网)

```bash
cd /path/to/tokenknows
zip -r tokenknows-plugin.zip tokenknows-plugin
# 上传 tokenknows-plugin.zip 到 claude.com/plugins
```

## 环境变量

**全部可选,带本机默认值** (`.mcp.json` 内置 `${VAR:-default}` 展开)。默认本机部署 (backend :8001 + web :5173 + demo 项目) **零配置可用**。

只有非默认场景才需要设置,且 **Cowork (桌面 app) 启动时只继承 GUI launch 时的 env (一般是 `~/.zshenv` / launchd `setenv`),不读 `~/.zshrc`**:

```bash
# macOS · launchctl setenv (永久, 重启后仍生效) — 按需设置, 不需要全设
launchctl setenv TOKENKNOWS_API_BASE "http://my-server:8001"      # backend 不在本机时
launchctl setenv TOKENKNOWS_API_TOKEN "tkk_..."                   # 后端开鉴权时 (Web → 项目设置 → MCP 接入 创建)
launchctl setenv TOKENKNOWS_DEFAULT_PROJECT "proj-..."            # 不用 demo 项目时
launchctl setenv TOKENKNOWS_WEB_BASE "http://my-server:5173"      # web 不在本机时 (view_url 前缀)
```

设完 **完全退出 Cowork (Cmd+Q) 再启动** 才生效 — 进程 env 是启动时的 snapshot。

## Cowork vs Code 行为差异

| 维度 | Claude Cowork | Claude Code |
|---|---|---|
| 触发 skill 主要方式 | 用户自然语言描述意图 | 用户敲 `/tokenknows:weekly` |
| Slash command 命名 | `/tokenknows:weekly` (同) | `/tokenknows:weekly` (同) |
| hook 支持 | Cowork 当前不支持 hooks | Code 支持 PreToolUse/PostToolUse/Stop |
| 多 session 状态 | Cowork 单 conversation 内 | Code 跨 session (tokenknows-watcher 监 `~/.claude/projects/*.jsonl`) |
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
返回 5 段 ADR markdown + Web 查看链接 (登录后打开)
```

如果 skill 没自动触发,显式说 `/tokenknows:adr`。

## 推荐配置 · 自动入库 (a + c 双保险)

Cowork **没有 SessionEnd hook** ([anthropics/claude-code#45514](https://github.com/anthropics/claude-code/issues/45514))。
为了让 Cowork 对话自动汇入 TokenKnows (不必每次说"记一笔"),建议两层兜底:

### a · MCP server instructions (零配置, 装上就生效)

MCP server 已经内置 instructions 引导 Cowork 在每个任务结束时主动调用
`submit_session_events(source_type="claude_cowork")`。装完 plugin 就生效, LLM
自主决定何时上报。

**完整性中等** — LLM 可能漏调,所以再加 c 兜底。

### c · Cowork scheduled task (定时补全, 推荐启用)

在 Cowork 内输:

```
/schedule
```

按提示设置一个每 30 分钟跑一次的任务,prompt 写:

```
请调用 tokenknows.submit_session_events,把过去 30 分钟内本 session 的
关键对话 (我的需求 / 你的方案 / 关键工具调用) 批量上报,source_type 设为
"claude_cowork", project_id 留空 (用默认)。每条 event 包含 title + content。
完成后简短确认即可,不必复述内容。
```

> ⚠️ 限制: Cowork scheduled task 只在 desktop app 开着 + 电脑唤醒时跑
> ([官方文档](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-claude-cowork))。
> 电脑关机/app 关闭时会跳过,下次唤醒补一次。

### 验证已接入

在 TokenKnows 工作台首页, "数据源" 卡片应出现 **🤝 Claude Cowork** 一行 (有事件后, dot 显示绿色 active)。
点开任意 Cowork 来源的 event 卡, 抽屉里 "来源" 字段显示 "Claude Cowork"。

## 排错

- **slash command 不出现**: 重启 Cowork; 确认 plugin 在 Plugins 设置里 enabled
- **MCP server 启动失败 (spawn uvx ENOENT)**: uvx 不在 Cowork 的 PATH 里 — 见上方"Cowork 专属 uvx PATH 注意";改完 `launchctl setenv` 后 Cmd+Q 重启 Cowork
- **"Backend not reachable"**: backend (8001) 没起;macOS firewall 检查 `127.0.0.1:8001` 是否被拦
- **"Authentication failed (401)"**: Web → 项目设置 → MCP 接入 创建 token → `launchctl setenv TOKENKNOWS_API_TOKEN "tkk_..."` → Cmd+Q 重启 Cowork
