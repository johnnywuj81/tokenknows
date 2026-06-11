---
name: tokenknows-distill
description: "把当前 Codex 会话蒸馏成结构化文档 (周报 / 技术方案 / ADR / 问题复盘 / 技术书籍 / Agent Skill / 知识图谱). 当用户说 '蒸馏 / 沉淀 / 生成周报 / 写个 ADR / 出个复盘 / 做知识图谱 / 把这次会话变成文档' 时使用. 通过 tokenknows MCP 工具触发后端 5-stage pipeline."
---

# TokenKnows 蒸馏

把研发会话沉淀成结构化知识资产。工具来自 `tokenknows` MCP server(在 `~/.codex/config.toml` 的 `[mcp_servers.tokenknows]` 配置)。

## 何时用

- 用户想把当前/最近的工作沉淀成文档:"写个周报"、"出个 ADR"、"复盘一下这次故障"、"做个知识图谱"
- 用户想把会话提炼成可复用 skill:"把这套做法存成 skill"

## 7 种文档类型

| type | 用途 |
|---|---|
| `weekly_report` | 本周进展 / Bug / 决策 / 风险 / 下周计划 |
| `tech_design` | 技术方案 6 部分 |
| `adr` | 架构决策记录 |
| `incident` | 问题复盘 |
| `book` | 长文档 (卷-章-节) |
| `agent_skill` | 蒸馏可复用 SKILL.md (需主题 `topic_hint`) |
| `knowledge_graph` | 实体关系图谱 |

## 关键步骤

1. **先确认会话已入库** (use `mcp__tokenknows__submit_session_events`):
   把当前会话的关键 turn 提交到 TokenKnows,作为蒸馏素材。
2. **触发蒸馏** (use `mcp__tokenknows__distill_document`):
   传 `type` (上表之一) + 可选 `time_window` (this_week / last_7_days / last_14_days / last_30_days)。
   `agent_skill` 类型必须带 `topic_hint` (单一主题,否则蒸不出可用 skill)。
3. **取结果** (use `mcp__tokenknows__list_assets` → `mcp__tokenknows__get_asset` →
   `mcp__tokenknows__get_asset_chapters`):
   告诉用户文档已生成,给出 asset 标题 + `view_url`(绝对 URL,前缀由 `TOKENKNOWS_WEB_BASE` 决定,默认 `http://127.0.0.1:5173`;登录 Web 工作台后查看/编辑/发布)。

## 好例子 / 坏例子

- 坏:用户说"写周报"→ 直接凭记忆编。**应** 先 submit 会话 + distill,让后端基于真实事件 + 证据链生成。
- 好:`distill_document(type="knowledge_graph", time_window="last_14_days")` → 返回 asset → `get_asset_chapters` 拿图谱节点/边 → 转述给用户。

## 注意

- 工具会 POST 到本地后端 (默认 `http://127.0.0.1:8001`),后端必须在跑。后端不通 / 401 缺 token / 404 项目不存在时,工具会返回带修复指引的双语错误信息 — 原样转述给用户即可。
- 蒸馏是后台 5 阶段流水线 (collect → outline → content → evidence → assess),`distill_document` 立即返回 generating 态,稍后 `get_asset` 轮询到 draft。
