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

## 依赖

- tokenknows-api 后端在 `http://127.0.0.1:8001` 跑
- `[mcp_servers.tokenknows]` 已配 (否则 skill 调不到工具)
