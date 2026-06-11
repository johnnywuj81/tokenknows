---
description: "把当前 session 中的故障排查 / Bug 修复过程蒸馏成故障复盘 (6 段: 现象/影响/根因/解决过程/改进/时间线)."
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **incident**:

incident 关键特征:
- session 应包含 **报警 / 报错 → 排查 → 修复** 的完整链
- 时间线信息很重要 (报警到恢复多久 / MTTR)

1. 拆 event 时强调时间戳 (occurred_at), 让后端能重建时间线
2. tag 用 `incident` / `bug_fix` / 严重度
3. `submit_session_events`
4. `distill_document(document_type="incident", time_window=$ARGUMENTS 默认 last_7_days)`
5. 展示 6 段
