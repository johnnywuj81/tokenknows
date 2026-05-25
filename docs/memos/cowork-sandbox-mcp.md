# Memo · Cowork Tab (Sandbox VM) MCP 接入方案

> **Status**: Draft · 决策待定
> **Created**: 2026-05-24
> **Author**: TokenKnows
> **Context**: T138 后 Cowork tab 集成 debug 总结 + B 方案技术设计

---

## 1. 问题

当前 tokenknows plugin 在 **Claude Code CLI** 和 **Claude Desktop Chat tab** 都能跑 (已验证),但**在 Claude Desktop Cowork tab 完全不可用**。需要决策是否做远程 MCP 改造让 Cowork tab 也接通。

## 2. Anthropic 三个 host 的差异 (实测)

| Host | 运行环境 | Plugin 配置文件 | 当前 tokenknows 是否可用 |
|---|---|---|---|
| Claude Code CLI | host (macOS 本机) | `--plugin-dir` flag / `~/.claude/plugins/cache/` | ✅ 已验证 (50K+ events 入库) |
| Claude Desktop **Chat** tab | host (macOS 本机) | `~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers` | ✅ 已配置, 重启后可用 |
| Claude Desktop **Cowork** tab | **隔离 Linux VM** ([source](https://www.productcompass.pm/p/claude-cowork-guide)) | sandbox 内 `cowork_plugins/marketplaces/` | ❌ 不可用 |
| Claude Desktop **Personal plugins** UI | (Code CLI 共享) | marketplace cache | ⚠️ **仅 metadata 展示**, Chat/Cowork 不读 |

**重要**: 之前以为"装好的 Personal plugin Chat tab 能直接用",**错的**。Chat tab MCP 必须显式在 `claude_desktop_config.json.mcpServers` 里声明 (有官方 [GitHub issue #42453](https://github.com/anthropics/claude-code/issues/42453) 承认这个分裂)。

## 3. Cowork sandbox 不兼容当前 plugin 的 3 个 blocker

| Plugin 依赖 (当前) | Cowork sandbox VM 里的现实 |
|---|---|
| `TOKENKNOWS_API_ROOT=/Users/wujun/TokenKnows/code/tokenknows-api` (host 路径) | ❌ Linux VM 文件系统里这路径不存在 |
| `PYTHONPATH` 指向 host repo + `python -m mcp_server` (本地代码加载) | ❌ VM 里没有 `mcp_server` Python package |
| `TOKENKNOWS_API_BASE=http://127.0.0.1:8002` (host loopback) | ❌ VM 的 `127.0.0.1` 不是 host 的 `127.0.0.1` |

**根因**: plugin 是 stdio MCP server, 假设 host 本地能 spawn Python + 访问 host loopback. 这个假设在隔离 sandbox 里全部失败.

## 4. 方案对比

### A. 让 Cowork sandbox 不接 plugin, 只用 Chat tab

| 维度 | 评估 |
|---|---|
| 工作量 | 0 — 已经做好 (Chat tab MCP 已配置) |
| 覆盖场景 | ❌ Cowork sandbox 内 Claude 自主跑代码/操作 desktop 的对话**无法被记录** |
| 适合 | 用户只把 Cowork 当 "更强的 Chat" 用, 不要求 sandbox 内对话入库 |

### B. 改造 MCP server 为远程 HTTP/SSE transport (推荐)

| 维度 | 评估 |
|---|---|
| 工作量 | 1-2 天 |
| 覆盖场景 | ✅ Code CLI / Chat tab / Cowork sandbox 三处统一接入, 一套实现 |
| 复杂度 | 中 — 涉及 transport 切换 + sandbox→host 网络桥接 + auth |
| Anthropic 官方 pattern | ✅ 官方 `knowledge-work-plugins` 全部走远程 connector |

### C. 当前不动, 等 Anthropic 提供 sandbox stdio plugin 支持

| 维度 | 评估 |
|---|---|
| 工作量 | 0 |
| 覆盖场景 | ❌ 无限期 |
| 风险 | Anthropic [issue #45514](https://github.com/anthropics/claude-code/issues/45514) 是 feature request, 无 ETA. Cowork 设计上就是隔离 sandbox, "本地 stdio plugin" 跟 sandbox 隔离哲学冲突, 可能永远不会支持 |

**推荐**: **B**. 一次工作消除三处分裂, 跟 Anthropic 官方 pattern 一致, 也消除 plugin 对 host 路径/Python env 的依赖 (副产品: Linux/Windows 用户也能用).

---

## 5. B 方案技术设计

### 5.1 Transport 切换

当前 [code/tokenknows-api/mcp_server/server.py](../../code/tokenknows-api/mcp_server/server.py) 用 FastMCP, 已支持 `--transport sse --port 8765` (见 `__main__.py`). 主要工作:

1. **新建 HTTP SSE endpoint** on backend `:8002` 直接挂载 MCP server, 复用 backend 进程, 不再单独跑 `python -m mcp_server`
2. plugin 端 `.mcp.json` 改成 `"transport": "sse"` + URL 指向 backend
3. 验证 stdio + SSE 行为对等

参考 [FastMCP SSE / Streamable HTTP](https://modelcontextprotocol.io/docs/develop/build-server) 官方文档. 注意 2026-03 后 spec 已经从 SSE 迁移到 **Streamable HTTP**, 应该用后者.

### 5.2 三处 host 配置示例

```json
// Code CLI plugin: tokenknows-plugin/.mcp.json
{
  "mcpServers": {
    "tokenknows": {
      "transport": "sse",
      "url": "http://127.0.0.1:8002/mcp/sse"
    }
  }
}

// Claude Desktop Chat: claude_desktop_config.json
{
  "mcpServers": {
    "tokenknows": {
      "transport": "sse",
      "url": "http://127.0.0.1:8002/mcp/sse"
    }
  }
}

// Cowork sandbox: 用 host.docker.internal 跨 sandbox→host
{
  "mcpServers": {
    "tokenknows": {
      "transport": "sse",
      "url": "http://host.docker.internal:8002/mcp/sse"
    }
  }
}
```

**关键**: 三处只有 URL 不同, Cowork 用 `host.docker.internal` 而非 `127.0.0.1` — sandbox VM 通过这个 DNS 名访问 host. 待验证 Cowork sandbox 是否支持这个 DNS (Docker Desktop 默认支持, Apple Hypervisor 待查).

### 5.3 Sandbox→Host 网络桥接

**待 verify**:
- Cowork sandbox 是 macOS Hypervisor (vz)? Linux UTM/QEMU? 不同 hypervisor 对 host 网络访问方式不同
- 默认是否允许 sandbox 访问 host 的 TCP 端口
- 是否需要 sandbox env var 提示 host IP (类似 `HOST_GATEWAY_IP`)

**Fallback**: 如果 sandbox 无法直接连 host loopback, 可以:
- (a) backend 监听 `0.0.0.0` 暴露到 LAN, sandbox 用 host LAN IP
- (b) 用 cloudflared/ngrok 把 backend 暴露成 public URL (有安全风险)
- (c) 在 sandbox 启动时注入 host 通过 SSH/socat tunnel

### 5.4 Auth

当前 plugin env 有 `TOKENKNOWS_API_TOKEN` (现为空, dev 模式). 改 SSE 后:

- 走 HTTP header `Authorization: Bearer <token>` 或 query param
- backend 应该校验 token (现在 8002 backend 是无 auth, dev 模式)
- 生产: 给每个 host 生成一次性 token, 写入对应配置

### 5.5 实施步骤 (估时 8-12 小时)

| 步骤 | 工作 | 时间 |
|---|---|---|
| 1 | 在 backend 加 mount MCP server SSE/Streamable HTTP endpoint | 2h |
| 2 | 单元测试: SSE endpoint 能正确 spawn MCP session, tool 调用 round-trip | 2h |
| 3 | 端到端测试 Code CLI 用新 SSE config (本地 verify ✅) | 1h |
| 4 | 端到端测试 Chat tab 用新 SSE config | 1h |
| 5 | 在 Cowork sandbox 内 install plugin + 验证 host.docker.internal 可达 | 2h |
| 6 | Cowork sandbox 端到端 (起对话, verify event 入库 source_type=claude_cowork) | 1h |
| 7 | (条件) 如 sandbox 不可达 host, 改 backend 监听 `0.0.0.0` + 加 token auth | 2h |
| 8 | 更新 INSTALL-COWORK.md + plugin marketplace 配置 + 删除 stdio 模式 | 1h |

### 5.6 验证方法

按 [verify-runtime-state](~/.claude/rules/common/verify-runtime-state.md) rule:

```bash
# 1. backend SSE endpoint reachable
curl -N http://127.0.0.1:8002/mcp/sse | head -5

# 2. host 上 Code CLI 起 plugin 后无新 python 子进程 (因为不 spawn stdio)
pgrep -fl "python -m mcp_server"   # 应为空

# 3. backend 进程接到 MCP session connection
tail -f ~/Library/Logs/tokenknows/api.err.log | grep -i "mcp"

# 4. Cowork sandbox 内 verify
# (在 Cowork tab 对话里说 "curl http://host.docker.internal:8002/api/v1/healthz")
# 应返 200

# 5. event 入库
sqlite3 .../state.sqlite "SELECT COUNT(*) FROM events WHERE source_type='claude_cowork';"
```

---

## 6. 已知风险 & 开放问题

| 风险 | 缓解 |
|---|---|
| Cowork sandbox 网络模型未文档化, `host.docker.internal` 可能不通 | 5.5 步骤 5 提前 verify; 失败走 fallback (LAN IP) |
| Streamable HTTP MCP transport spec 还在演进 (2026-03 替换 SSE) | 用 FastMCP 抽象层屏蔽 spec 变化; pin SDK version |
| backend 进程承载 MCP session 可能影响 API 响应延迟 | 单独路由 `/mcp/*` 不跟业务 endpoint 共享 worker pool |
| `127.0.0.1:8002` 改成 `0.0.0.0` 后, LAN 上其它设备能访问 backend | 必须加 auth token; firewall 限定来源 IP |
| stdio plugin 用户 (有些人还在用) 升级路径 | 同时保留 stdio 入口一段时间, 加 deprecation warning |

## 7. 决策点

- [ ] **要不要做 B?** (推荐: 做, 一劳永逸)
- [ ] **何时做?** (建议 v2.1, 当前 v2.0 + Code CLI/Chat tab 已经可用, 不阻塞日常使用)
- [ ] **要不要保留 stdio 模式作为 fallback?** (建议: 保留 3 个月做迁移过渡)

---

## 8. 参考资料

- [Manage Claude Cowork plugins (Anthropic)](https://support.claude.com/en/articles/13837433-manage-claude-cowork-plugins-for-your-organization)
- [Getting Started with Local MCP Servers on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Claude Cowork: Ultimate Guide for PMs (sandbox 描述)](https://www.productcompass.pm/p/claude-cowork-guide)
- [Discover and install prebuilt plugins (Claude Code docs)](https://code.claude.com/docs/en/discover-plugins)
- [Plugin marketplaces — plugin source field spec](https://code.claude.com/docs/en/plugin-marketplaces)
- [Connect Claude Desktop to Local MCP Servers (dev.to)](https://dev.to/danishashko/connect-claude-desktop-to-local-mcp-servers-2ia8)
- [GitHub anthropics/claude-code#42453: Custom local MCP tools disabled in Cowork](https://github.com/anthropics/claude-code/issues/42453)
- [GitHub anthropics/claude-code#45514: Plugin/hook system parity (Code/Cowork)](https://github.com/anthropics/claude-code/issues/45514)
- [GitHub anthropics/knowledge-work-plugins (sandbox-native examples)](https://github.com/anthropics/knowledge-work-plugins)
- [Model Context Protocol — Connect to local servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers)

## 9. 本 memo 的 ground truth (来自本次 session 实测)

| 检查项 | 实测结果 |
|---|---|
| Cowork sandbox `cowork_plugins/marketplaces/` 是否含 tokenknows | ❌ 只有 `knowledge-work-plugins/` (Anthropic 官方) |
| Cowork sandbox `tokenknows-inline/` 目录文件数 | 0 (空目录) |
| 系统跑的 `python -m mcp_server` 进程的 parent | 全是 `claude.app/Contents/MacOS/claude` (**Code CLI binary**), 没有任一个是 Claude Desktop GUI spawn |
| `claude_desktop_config.json.mcpServers` 默认值 | `{}` (空 — Personal plugins 不自动写入这里) |
| backend `events` 表 `claude_cowork` 事件数 | 0 (即使用户在 Cowork tab 起过多次对话) |
