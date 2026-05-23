# TokenKnows Plugins · Marketplace

Claude Code / Cowork plugins · 把 session 蒸馏成结构化文档。

## 安装

### Claude Code

```bash
# 添加 marketplace
claude /plugin marketplace add johnnywuj81/tokenknows@main

# 当 marketplace 在 monorepo 子目录时, 指定 path
# (本仓库 marketplace 在 code/tokenknows-plugins/)
claude /plugin marketplace add johnnywuj81/tokenknows@main:code/tokenknows-plugins

# 装 plugin
claude /plugin install tokenknows
```

### Claude Cowork

在 Cowork 设置 → Plugins → "Add marketplace" 输入 `johnnywuj81/tokenknows` 即可。详见 [claude-code/INSTALL-COWORK.md](./claude-code/INSTALL-COWORK.md)。

### 本地 / 离线测试

```bash
git clone https://github.com/johnnywuj81/tokenknows
cd tokenknows
claude --plugin-dir code/tokenknows-plugins/claude-code
```

## 前置: 跑起 tokenknows-api 后端

plugin 需要后端在本地或可达地址提供 MCP server + REST API:

```bash
cd code/tokenknows-api
.venv/bin/uvicorn app.main:app --port 8001
```

详见 [tokenknows-api README](../tokenknows-api/README.md)。

## 包含的 plugins

| name | 描述 |
|---|---|
| `tokenknows` | 7 类文档蒸馏 (周报 / 技术方案 / ADR / 复盘 / 书籍 / Skill / 知识图谱). 单 plugin 双 host (Code + Cowork) |

## 环境变量

启动 Claude Code / Cowork **之前** 必须 export:

```bash
export TOKENKNOWS_API_ROOT="$HOME/TokenKnows/code/tokenknows-api"  # 绝对路径
export TOKENKNOWS_API_BASE="http://127.0.0.1:8001"
export TOKENKNOWS_DEFAULT_PROJECT="demo-project"
export TOKENKNOWS_API_TOKEN=""  # 公网部署后填 JWT
```

macOS Cowork 桌面 app 需要用 `launchctl setenv` 而非 `~/.zshrc` (Cowork 不读 shell rc)。详见 INSTALL-COWORK.md。

## 后台 session 自动采集 (可选)

T118 提供 daemon, 后台监听 `~/.claude/projects/*.jsonl` 增量上报 events,
无需用户主动 `/tk:weekly` 也能持续积累素材:

```bash
# 一次扫
python -m mcp_server.daemon --once

# 后台轮询 (每 30s)
nohup python -m mcp_server.daemon > /tmp/tokenknows-watcher.log 2>&1 &
```

## 升级

```bash
claude /plugin marketplace update tokenknows
claude /plugin update tokenknows
```

## License

MIT
