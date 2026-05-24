---
description: 把当前 Claude session 蒸馏成技术方案文档 (6 段: 背景/目标/设计思路/关键决策/风险与取舍/实施计划).
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **tech_design**:

1. 拆 event 时聚焦 **设计推理** 而非操作流水 (用户提需求 → Claude 给方案 → 取舍讨论 → 选定方案)
2. `submit_session_events` (tag 含 `tech_design`, `design_decision`)
3. `distill_document(document_type="tech_design", time_window=$ARGUMENTS 默认 this_week)`
4. 轮询完成
5. 展示 6 段 markdown
