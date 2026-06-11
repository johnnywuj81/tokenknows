---
description: 把当前 session 蒸馏成知识图谱 (KG) - 4 类节点 (person/event/concept/artifact) + 6 类边. 适合关系密集的复盘 / 跨团队事件 / 季度回顾.
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **knowledge_graph**:

KG 关键价值:
- 跨实体关系一目了然 (谁推动了什么 / 什么依赖什么 / 哪些决策冲突)
- 跨文档实体合并 (Alice 在多个 KG 里自动合一)
- 浏览器内可视化拖拽探索

适合用 KG 的对话:
- 涉及 **多人**, **多决策**, **多文档/工具**
- 故障复盘 + 后续修复 (caused_by 链)
- 季度回顾 / 大项目 wrap-up

1. 拆 event 时给每个实体清晰锚定 (谁 / 什么时候 / 做了什么) - 后端会基于此抽节点
2. `submit_session_events`
3. `distill_document(document_type="knowledge_graph", time_window=$ARGUMENTS 默认 last_30_days)`
4. 轮询完成
5. 展示:
   - 节点数 / 边数 / 4 类节点分布
   - 用 ASCII art 示意一两条关键关系 (e.g. `Alice --authored_by--> PR#127 --depends_on--> retry_jitter`)
   - 给浏览器 URL 让用户看完整可视化 (view_url 是绝对 URL, 前缀由 TOKENKNOWS_WEB_BASE 决定; 需登录 Web 工作台)
6. 如果用户问 "X 在哪些文档里也出现", 调 `search_entity(query="X")`
