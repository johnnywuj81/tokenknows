---
description: 列出当前 project 已蒸馏的文档. 可按类型/状态过滤. 用于回顾历史结果.
---

调 MCP tool `list_assets`:

```
asset_type: $ARGUMENTS  // 可选 weekly_report/tech_design/adr/incident/book/agent_skill/knowledge_graph
limit: 20  // 默认
```

展示方式:
```
[type] title (status) · v{version} · {updated_at}
   id: asset-xxx
   metrics: coverage=0.88 / citation=0.72
```

如果用户想看具体某条, 提示 "调 /tokenknows:open asset-xxx" 或者 "在浏览器打开 {view_url}" (绝对 URL, 需登录 Web 工作台)。

无 `$ARGUMENTS` 时列出全部 7 类 asset (按时间倒序). 有 `$ARGUMENTS` 时按 type 过滤.
