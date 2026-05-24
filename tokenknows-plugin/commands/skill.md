---
description: 从当前 session 蒸馏出可复用的 Agent Skill (SKILL.md 风格), 可后续落地到 ~/.claude/skills/ 自己用.
---

按 `tokenknows:distill` skill 的标准流程,把当前 session 蒸馏成 **agent_skill**:

适用场景:
- session 中 Claude 解决了一个 **可重复** 的问题 (e.g. "如何修 React Flow MiniMap 白板")
- 用户想把这次的解决过程沉淀成下次自动调用的 skill

蒸馏出来的 SKILL.md 结构:
- frontmatter: description (含 trigger 关键词)
- 适用场景
- 核心原则
- 关键步骤
- 好例子 / 坏例子
- 相关 skill

1. session 必须有明确的 "可复用工作流"; 如果只是闲聊 / 一次性问题, 拒绝并建议用 weekly_report
2. `submit_session_events`
3. `distill_document(document_type="agent_skill")`
4. 展示蒸馏出的 SKILL.md
5. 询问用户是否要 `cp` 到 `~/.claude/skills/<name>/SKILL.md` 立即生效
