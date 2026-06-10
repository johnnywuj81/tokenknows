---
name: tokenknows-knowledge
description: "检索 TokenKnows 项目知识库 —— 跨会话的已蒸馏文档与实体关系图谱. 当用户问 '我们之前怎么决定的 / 这个模块谁改过 / 有没有相关 ADR / 查一下 X 实体 / 列一下知识库文档' 时使用. 通过 tokenknows MCP 工具查询后端."
---

# TokenKnows 知识检索

查询跨会话沉淀的项目知识资产。工具来自 `tokenknows` MCP server。

## 何时用

- 用户想回溯历史决策:"我们之前为什么选 ClickHouse"、"有没有相关 ADR"
- 用户想查实体:"X 模块谁改过"、"搜一下 Y 这个概念"
- 用户想看知识库里有什么:"列一下已生成的文档"

## 关键步骤

1. **列资产** (use `mcp__tokenknows__list_assets`):
   按 type / 时间窗筛选项目里已蒸馏的文档 (周报 / ADR / KG / ...)。
2. **读详情** (use `mcp__tokenknows__get_asset` + `mcp__tokenknows__get_asset_chapters`):
   拿到某份文档的章节正文 + 证据链。
3. **跨文档实体搜索** (use `mcp__tokenknows__search_entity`):
   传 `query` (+ 可选 `entity_type`: person / concept / artifact / event),
   在知识图谱里找实体 + 它出现在哪些文档。

## 好例子 / 坏例子

- 坏:用户问"我们之前怎么决定数据库的"→ 凭印象答。**应** `search_entity("数据库选型")` 或
  `list_assets(type="adr")` 找到真实 ADR 再答,带出处。
- 好:`search_entity(query="ClickHouse")` → 返回相关实体 + 所在 ADR/KG → 给用户带链接的答案。

## 注意

- 只读操作,不改知识库。
- 依赖本地后端 (`http://127.0.0.1:8001`) 在跑。
