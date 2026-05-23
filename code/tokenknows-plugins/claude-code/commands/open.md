---
description: 读单个已蒸馏 asset 的完整内容. 用法 /tokenknows:open <asset_id>
---

**先校验 `$ARGUMENTS`**:
- 期望格式: `asset-<12-16 hex chars>` 或 `demo-{kg,wr}-NNN` (e.g. `asset-3d6cf67d96`, `demo-kg-001`)
- 若含 `;`, `|`, `&`, `$`, `\``, 引号, 空格 或换行 等可疑字符, **拒绝** 并提示 "asset_id 格式异常, 用 /tokenknows:list 查可用 id"
- 若为空, 提示 "请传 asset_id, 用 /tokenknows:list 看可用 id"

校验通过后调 MCP tool `get_asset_chapters("$ARGUMENTS")`,展示所有章节 markdown.

如果是 knowledge_graph 类型, 额外:
- 简述节点/边统计
- 询问用户是否要 `search_entity` 查特定实体跨文档出现
