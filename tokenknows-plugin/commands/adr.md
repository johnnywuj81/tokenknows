---
description: 把当前 session 中的架构决策蒸馏成 ADR (Architecture Decision Record, 5 段: 上下文/决策/备选/后果/状态).
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **adr**:

ADR 关键特征:
- 必须有 **明确决策点** (e.g. "用 React Flow 而非 G6 做 KG 可视化")
- 必须有 **备选方案** + 取舍理由
- 不是流水, 是 "为什么这么选" 的浓缩

1. 检查 session 里是否有真实架构决策; 没有就告诉用户 "这次 session 没有明显架构决策, 建议改用 weekly_report"
2. 拆 event 聚焦决策点 (备选 N 个 / 选了 X / 因为 Y / 后果 Z)
3. `submit_session_events`
4. `distill_document(document_type="adr")` ← 注意 ADR 时间窗一般不重要
5. 展示
