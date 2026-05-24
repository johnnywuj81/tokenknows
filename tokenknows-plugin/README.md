# tokenknows — Claude Code / Cowork Plugin

把当前 Claude session 蒸馏成 **7 种结构化文档** (周报 / 技术方案 / ADR / 故障复盘 / 技术书籍 / Skill / 知识图谱),通过 MCP 接 [tokenknows-api](https://github.com/johnnywuj81/tokenknows) 后端 5-stage LLM pipeline。

> 同时支持 **Claude Cowork** (官方 plugin schema 完全兼容,一份 plugin 双 host 用)。Cowork 安装方式详见 [INSTALL-COWORK.md](./INSTALL-COWORK.md)。

## 能干什么

```
你: "把我们这次的对话整理成 ADR"
   ↓
Claude:
  · 拆 session → 5 个 event
  · 调 submit_session_events
  · 调 distill_document(type=adr)
  · 轮询 60s
  · 展示 5 段 ADR markdown
  · 给你后端 URL 浏览器看富文本
```

## 安装

### 前置: 先把 backend 和 MCP server 跑起来

```bash
# 1. clone tokenknows
git clone https://github.com/johnnywuj81/tokenknows.git
cd tokenknows/code/tokenknows-api

# 2. 装 deps
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install "mcp[cli]>=1.27"

# 3. 配 .env.local (至少要 ANTHROPIC_API_KEY)
cp .env.local.example .env.local
# 编辑 .env.local 填 ANTHROPIC_API_KEY

# 4. 启 backend
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### 装 plugin 到 Claude Code

**方式 1 · 本地测试 (开发用)**:

```bash
# 关键: Claude Code 启动时从 host shell env 取 ${VAR} 替换 .mcp.json,
# 所以这 4 个变量必须在启动 claude 前 export 到 shell.
# 永久生效可写入 ~/.zshrc 或 ~/.bashrc.

export TOKENKNOWS_API_ROOT="/path/to/tokenknows/code/tokenknows-api"   # tokenknows-api 仓绝对路径 (PYTHONPATH 用)
export TOKENKNOWS_API_BASE="http://127.0.0.1:8001"                     # backend URL
export TOKENKNOWS_DEFAULT_PROJECT="proj-demo-001"                      # 默认 project_id (与 web demo 项目一致)
export TOKENKNOWS_API_TOKEN=""                                         # JWT bearer (本地默认空)

# 用 --plugin-dir 加载本 plugin
cd /path/to/tokenknows/tokenknows-plugin
claude --plugin-dir .
```

**关键提示**: 不要省略 `export`。`.mcp.json` 不支持 `${VAR:-default}` 默认值语法 (官方文档只承诺 `${VAR}` 替换),如果你不 export, MCP server 启动时这些变量会是空字符串导致 backend 连接失败。

启动后输入 `/help` 应该能看到 `/tokenknows:weekly` 等 8 个 slash command。

**方式 2 · 从 marketplace 装** (推荐):

```
/plugin marketplace add johnnywuj81/tokenknows@main
/plugin install tokenknows
```

> marketplace manifest 在 repo root (`.claude-plugin/marketplace.json`),Cowork
> 也用同一份。Cowork UI 上直接输 `johnnywuj81/tokenknows` 即可。

## 用法

| 命令 | 文档类型 | 适合场景 |
|---|---|---|
| `/tokenknows:weekly [time_window]` | 项目周报 | 一周的多个 task 汇总 |
| `/tokenknows:design` | 技术方案 | 含设计推理 + 取舍 |
| `/tokenknows:adr` | 架构决策记录 | 有明确的"为什么选 X 不选 Y" |
| `/tokenknows:incident` | 故障复盘 | bug/故障排查链 |
| `/tokenknows:book` | 技术书籍 | 长 deep dive (10万字+) |
| `/tokenknows:skill` | Agent Skill | 可复用的工作流沉淀 |
| `/tokenknows:kg` | 知识图谱 | 关系密集 / 跨实体 |
| `/tokenknows:list [type]` | — | 列已有蒸馏结果 |
| `/tokenknows:open <asset_id>` | — | 读单个 asset 完整内容 |

也可以让 Claude 自动判断 — skill `tokenknows:distill` 会按用户意图触发:

```
你: 我们这次讨论的"超时策略"蒸馏成 ADR
   ↓
Claude 自动调用 distill skill, 走 ADR 流程
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TOKENKNOWS_API_BASE` | `http://127.0.0.1:8001` | backend URL |
| `TOKENKNOWS_API_ROOT` | (无) | tokenknows-api 仓的绝对路径 (PYTHONPATH 用) |
| `TOKENKNOWS_DEFAULT_PROJECT` | `proj-demo-001` | 默认 project_id (web demo 项目) |
| `TOKENKNOWS_API_TOKEN` | (无) | JWT bearer; 公网部署 backend 时必填 |

## 验证

```bash
# 1. backend alive?
curl http://127.0.0.1:8001/api/v1/projects/proj-demo-001/assets

# 2. MCP server stdio 能 list tools?
cd $TOKENKNOWS_API_ROOT
python -m mcp_server --help

# 3. Claude Code 装 plugin 后 /help 能看到 tokenknows:* 命令
```

## 排错

- **slash command 找不到**: 跑 `/reload-plugins`,或重启 Claude Code
- **MCP tool 报 NETWORK_ERROR**: backend (8001) 没起,跑 `uvicorn app.main:app --port 8001`
- **distill 超时**: 后端 LLM 调用慢/quota,看 backend log;5 分钟后 sweep 会 mark draft + 写 parse_error
- **events 全被 skipped**: 后端 dedup 命中相同 content_hash,正常 (重复 session 不会重复入库)

## 架构

```
Claude Code
   ↓ (stdio MCP)
tokenknows-mcp (Python, FastMCP)
   ↓ (HTTP)
tokenknows-api (FastAPI)
   ↓ (LLM)
Anthropic / OpenAI / Ollama
```

MCP server 6 个 tool + 1 prompt + 1 resource template,详见 `tokenknows-api/mcp_server/server.py`。

## License

MIT
