# TokenKnows · Codex marketplace 插件

把 TokenKnows 以 **Codex 原生插件**形态接入(出现在 Codex 的 Plugins 市场里),
跟 Claude Code 的 `tokenknows-plugin` 对标。

## 这是什么

一个**本地 marketplace**,内含 `tokenknows` 插件:
- `.agents/plugins/marketplace.json` — 市场清单 (列出插件)
- `plugins/tokenknows/.codex-plugin/plugin.json` — 插件清单 (市场 UI 展示元数据)
- `plugins/tokenknows/skills/` — 两个 skill:
  - `tokenknows-distill` — 把会话蒸馏成文档 (周报/ADR/KG/...)
  - `tokenknows-knowledge` — 检索项目知识库 + 实体图谱

## 工具从哪来

插件的 skill **调用 `tokenknows` MCP server 的工具**
(`submit_session_events` / `distill_document` / `list_assets` / `get_asset` /
`get_asset_chapters` / `search_entity`)。

所以需要**两样都配**:
1. `[mcp_servers.tokenknows]` 在 `~/.codex/config.toml`(提供工具)
2. `[marketplaces.tokenknows]` 在 `~/.codex/config.toml`(提供市场里的插件 + skills)

> 架构同 Claude Code:插件 = MCP(工具) + skills/commands(何时怎么用)。

## 安装 (本地 marketplace)

在 `~/.codex/config.toml` 加:

```toml
[marketplaces.tokenknows]
source_type = "local"
source = "~/TokenKnows/codex-plugin"   # 改成你的 clone 路径
```

然后**完全退出 + 重开 Codex**(Cmd+Q)。Plugins 市场里筛选 "All"(非 "Built by OpenAI")
应能看到 **TokenKnows**,点 install。

## 卸载

删掉 config.toml 里 `[marketplaces.tokenknows]` 块 + 重开 Codex。

## 依赖 (前置链与 Claude Code 插件一致)

1. **tokenknows-api 后端**在 `http://127.0.0.1:8001` 跑(部署见[主仓 README](https://github.com/johnnywuj81/tokenknows))
2. **Web 工作台**在 `http://localhost:5173` 跑 — 蒸馏结果在这里富文本查看;注册/登录后在**项目设置 → MCP 接入**自助创建 API token(后端开鉴权时需要)
3. **uv** 已装(MCP server 经 `uvx` 从 PyPI 拉起,不需要 clone 仓库)
4. `[mcp_servers.tokenknows]` 已配(否则 skill 调不到工具):

```toml
# ~/.codex/config.toml — Codex 不支持 ${VAR:-default} 展开, 写字面量
[mcp_servers.tokenknows]
command = "uvx"
args = ["tokenknows-mcp==0.3.0"]

[mcp_servers.tokenknows.env]
TOKENKNOWS_API_BASE = "http://127.0.0.1:8001"      # backend
TOKENKNOWS_API_TOKEN = ""                           # 开鉴权时填 tkk_... (Web → 项目设置 → MCP 接入)
TOKENKNOWS_DEFAULT_PROJECT = "proj-demo-001"        # 默认项目
TOKENKNOWS_WEB_BASE = "http://127.0.0.1:5173"      # view_url 链接前缀
```
