---
description: 把当前 session 蒸馏成长文档 / 技术书籍 (卷-章-节 嵌套大纲, 10 万字+). 适合 deep dive 类长对话.
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **book**:

**注意**: book 类型生成耗时较长 (5-10 分钟), 调多次 LLM 顺序生成各章, 适合:
- 长达数小时的深入对话
- 单一主题 deep dive (e.g. "MCP 协议从原理到实现")
- 想沉淀成参考材料的内容

短对话不要用 book, 用 weekly_report / tech_design 更经济.

1. 提示用户 "book 类型预计 5-10 分钟, 是否继续?"
2. 拆 event 时按主题分组 (book outline 阶段 LLM 会再次组织成卷/章)
3. `submit_session_events`
4. `distill_document(document_type="book", time_window=$ARGUMENTS 默认 last_30_days)`
5. 轮询时长放宽到 600s
6. 展示时先列卷-章 outline, 再问用户要看哪章
