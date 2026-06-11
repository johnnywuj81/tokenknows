# tokenknows — Claude Code / Cowork Plugin

把当前 Claude session 蒸馏成 **7 种结构化文档** (周报 / 技术方案 / ADR / 故障复盘 / 技术书籍 / Skill / 知识图谱),通过 MCP 接 [tokenknows-api](https://github.com/johnnywuj81/tokenknows) 后端 5-stage LLM pipeline,蒸馏结果在 Web 工作台 (`tokenknows-web`) 里富文本查看、审批、发布。

> 同时支持 **Claude Cowork** (官方 plugin schema 完全兼容,一份 plugin 双 host 用)。Cowork 安装方式详见 [INSTALL-COWORK.md](./INSTALL-COWORK.md)。
>
> 版本对应: 插件 `2.2.0` ⇄ PyPI [`tokenknows-mcp`](https://pypi.org/project/tokenknows-mcp/) `0.3.0` (`.mcp.json` 里 pin 死,随插件 release 同步 bump)。

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
  · 给你 Web 工作台 URL,浏览器登录后看富文本 + 证据链
```

## 5 分钟跑通 (新用户照抄即可)

```bash
# 0. 前置: python3.11+ / node 20+ / git / uv
curl -LsSf https://astral.sh/uv/install.sh | sh    # 或 brew install uv

# 1. backend
git clone https://github.com/johnnywuj81/tokenknows.git
cd tokenknows/code/tokenknows-api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.local.example .env.local                    # 填 ANTHROPIC_API_KEY, 或保持 Ollama 全本地
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 &

# 2. web 工作台
cd ../tokenknows-web && npm install && npm run dev &   # http://localhost:5173 (代理 /api → 8001)

# 3. 浏览器开 http://localhost:5173 → 注册/登录 → 选项目
#    → 项目设置 → MCP 接入 → 创建 API token → 一键复制环境变量块

# 4. 只有非默认场景才需要 export (默认本机部署零配置):
# export TOKENKNOWS_API_TOKEN="tkk_..."             # 后端开了 AUTH_MODE=required 时
# export TOKENKNOWS_DEFAULT_PROJECT="proj-..."      # 不用 demo 项目时

# 5. 装插件 (在 claude 里):
#    /plugin marketplace add johnnywuj81/tokenknows
#    /plugin install tokenknows@tokenknows
#    重启 claude

# 6. 验证:
#    /tokenknows:list        → 资产列表或干净的空结果 (不应有堆栈)
#    /tokenknows:weekly      → 蒸馏周报; 返回的 view_url 是完整链接, 登录后浏览器直接打开
```

## 安装详解

### 第 1 步 · 部署 backend (必须)

```bash
git clone https://github.com/johnnywuj81/tokenknows.git
cd tokenknows/code/tokenknows-api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.local.example .env.local      # 至少填 ANTHROPIC_API_KEY (或配 Ollama 全离线)
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### 第 2 步 · 启动 Web 工作台 (强烈推荐)

蒸馏结果的富文本阅读、证据链回溯、审批发布都在这里;插件返回的 `view_url` 也指向这里。

```bash
cd tokenknows/code/tokenknows-web
npm install && npm run dev            # http://localhost:5173
```

### 第 3 步 · 注册/登录 + 拿 token

浏览器打开 `http://localhost:5173` → 注册账号并登录 → 选 (或建) 项目 → **项目设置 → MCP 接入**:

- 创建 API token (`tkk_` 前缀,**只显示一次**,可随时撤销)
- 一键复制为插件准备好的环境变量块 (`TOKENKNOWS_API_BASE` / `TOKENKNOWS_API_TOKEN` / `TOKENKNOWS_DEFAULT_PROJECT`)
- 面板上的 "最近使用" 时间 = 插件已成功连上的信号

> 默认本机部署 (`AUTH_MODE=open`) 不强制 token,跳过此步也能跑;公网部署后端时必须配。

### 第 4 步 · 装 uv

插件经 `uvx` 从 PyPI 拉起 MCP server (`tokenknows-mcp`),不再需要 clone 仓库:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # 或 brew install uv
```

<details>
<summary>不想装 uv? pip 替代方案</summary>

```bash
pip install tokenknows-mcp
claude mcp add tokenknows -- tokenknows-mcp   # user 级注册, 绕开插件内置 .mcp.json
```

</details>

### 第 5 步 · 装插件

```
/plugin marketplace add johnnywuj81/tokenknows
/plugin install tokenknows@tokenknows
```

重启 Claude Code,`/help` 应出现 `/tokenknows:weekly` 等 9 个 slash command,`/mcp` 里 tokenknows 显示 connected。

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

全部**可选,带本机默认值** (`.mcp.json` 用官方支持的 `${VAR:-default}` 语法展开):

| 变量 | 默认值 | 何时需要改 |
|---|---|---|
| `TOKENKNOWS_API_BASE` | `http://127.0.0.1:8001` | backend 部署在别处 |
| `TOKENKNOWS_API_TOKEN` | (空) | backend 开 `AUTH_MODE=required`;在 Web → 项目设置 → MCP 接入 创建 |
| `TOKENKNOWS_DEFAULT_PROJECT` | `proj-demo-001` | 不用 demo 项目;项目 ID 在 Web 项目设置可见 |
| `TOKENKNOWS_WEB_BASE` | `http://127.0.0.1:5173` | Web 工作台部署在别处 (决定 `view_url` 链接前缀) |

改默认值的方式:启动 claude 前在 shell export (写 `~/.zshrc` 永久生效)。

## 自动入库 · session watcher (可选)

不想每次手动说"记一笔"?PyPI 包自带 `tokenknows-watcher` 守护进程:监听 `~/.claude/projects/*.jsonl`,增量上传对话轮次 (content_hash 去重,状态存 `~/.tokenknows-watcher.json`),让 `/tokenknows:weekly` 永远有料。

```bash
uvx --from tokenknows-mcp tokenknows-watcher              # 前台, 30s 轮询
uvx --from tokenknows-mcp tokenknows-watcher --interval 60
uvx --from tokenknows-mcp tokenknows-watcher --once       # cron 模式
```

读同一套 `TOKENKNOWS_*` 环境变量。

## 本地开发 (贡献者)

MCP server 源码真身在 `code/tokenknows-api/mcp_server/` (PyPI 包 `tokenknows-mcp` 由 `code/tokenknows-mcp/build.sh` rsync 打包)。要让插件跑本地源码而不是 PyPI 版:

```bash
export TOKENKNOWS_API_ROOT="/abs/path/to/tokenknows/code/tokenknows-api"
# .mcp.json 把它透传为 PYTHONPATH, 优先于 uvx 装的包 → import mcp_server 走本地源码
cd tokenknows-plugin && claude --plugin-dir .
```

不设 `TOKENKNOWS_API_ROOT` 时 PYTHONPATH 为空,无副作用。**注意**: 设了它就会覆盖 PyPI 版,调试完记得 unset。

## 验证

```bash
# 1. backend alive?
curl http://127.0.0.1:8001/api/v1/projects/proj-demo-001/assets

# 2. MCP server 能起?
uvx tokenknows-mcp==0.3.0 --help

# 3. Claude Code 装 plugin 后 /help 能看到 tokenknows:* 命令, /mcp 显示 connected
```

## 排错

- **slash command 找不到**: 跑 `/reload-plugins`,或重启 Claude Code
- **MCP server 启动失败 / spawn uvx ENOENT**: 没装 uv → `curl -LsSf https://astral.sh/uv/install.sh | sh`,重启 claude
- **"Backend not reachable at ..."**: backend (8001) 没起,跑 `uvicorn app.main:app --port 8001`;或 `TOKENKNOWS_API_BASE` 指错
- **"Authentication failed (401)"**: 后端开了鉴权但没配 token → Web → 项目设置 → MCP 接入 创建,export `TOKENKNOWS_API_TOKEN` 后重启 claude (或 `/mcp` reconnect)
- **"Project ... not found (404)"**: `TOKENKNOWS_DEFAULT_PROJECT` 指向不存在的项目;项目 ID 在 Web 项目设置可见
- **distill 超时**: 后端 LLM 调用慢/quota,看 backend log;5 分钟后 sweep 会 mark draft + 写 parse_error
- **events 全被 skipped**: 后端 dedup 命中相同 content_hash,正常 (重复 session 不会重复入库)
- **view_url 打不开**: Web 前端 (5173) 没起,或 `TOKENKNOWS_WEB_BASE` 指错;打开后需要登录

## 架构

```
Claude Code / Cowork
   ↓ (stdio MCP, uvx 拉起)
tokenknows-mcp (PyPI · Python · FastMCP)     ← 源码真身: code/tokenknows-api/mcp_server
   ↓ (HTTP + Bearer tkk_ token)
tokenknows-api (FastAPI :8001)
   ↓ (LLM)                    ↑ (浏览器, 登录)
Anthropic / OpenAI / Ollama   tokenknows-web (:5173)
```

MCP server 6 个 tool + 1 prompt + 1 resource template,详见 `tokenknows-api/mcp_server/server.py`。

## License

MIT
