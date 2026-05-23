---
description: 把当前 Claude session 蒸馏成项目周报 (本周进展 / Bug / 决策 / 风险 / 下周计划). 可附时间窗参数 (this_week/last_week/last_7_days).
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **weekly_report**:

1. 拆 3-10 条 event (用户需求 / 方案 / 关键决策 / 验证结果)
2. `submit_session_events`
3. `distill_document(document_type="weekly_report", time_window="$ARGUMENTS" 默认 this_week)`
4. 轮询 `get_asset` 到 `draft`
5. `get_asset_chapters` 展示 5 段 markdown

参数 `$ARGUMENTS` 可选: `this_week` / `last_week` / `last_7_days` / `last_14_days` / `last_30_days`. 缺省 `this_week`.
