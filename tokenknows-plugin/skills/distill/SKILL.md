---
description: 把当前 Claude session 的对话蒸馏成结构化文档 (周报 / 技术方案 / ADR / 故障复盘 / 技术书籍 / Skill / 知识图谱). 用户说 "蒸馏" "总结成 ADR" "生成周报" "出 KG" 等表达时调用. 走 tokenknows MCP 后端 5-stage pipeline.
---

# Distill Session

把当前 Claude session 蒸馏成 TokenKnows 后端的结构化文档之一。

## 用户意图判断

用户说下列任一表达,即应调用此 skill:

| 用户说 | 推断文档类型 |
|---|---|
| "蒸馏 / 总结 / 整理" 这次对话 | 让用户选, 默认 `weekly_report` |
| "出周报" / "生成周报" / "weekly" | `weekly_report` |
| "技术方案" / "设计文档" / "tech design" | `tech_design` |
| "ADR" / "架构决策" / "决策记录" | `adr` |
| "复盘" / "故障复盘" / "postmortem" | `incident` |
| "技术书籍" / "教程" / "long-form" | `book` |
| "蒸馏 skill" / "提炼专家技能" | `agent_skill` |
| "知识图谱" / "KG" / "实体关系" | `knowledge_graph` |

如果用户没明示,优先问一句 "你想蒸馏成哪种类型?周报 / 技术方案 / ADR / 复盘 / 书籍 / Skill / 知识图谱?",然后再走流程。

## 标准流程 (5 步)

### Step 1 · 整理本次 session 的关键事件

把对话拆成 3-10 条 **event** (每条聚焦一个语义单元):
- 用户提的需求 / 问题 / 决策点
- Claude 给出的方案 / 关键代码 / 取舍说明
- 重要工具调用 (e.g. Edit/Bash 执行的 PR 合并、测试结果)

每条 event 形如:
```json
{
  "external_id": "<session_uuid>-<msg_index>",
  "source_ref": "<session_uuid>",
  "event_type": "ai_conversation_turn",  // 或 tool_call/code_change
  "content": "<对话片段或代码变更摘要>",
  "title": "<一句话标题>",
  "author_name": "user" 或 "Claude",
  "tags": ["关键词1", "关键词2"]
}
```

**关键: external_id 务必唯一** (同 session_uuid + msg_index)避免后端 dedup 时丢失。

### Step 2 · 批量提交 events

调 MCP tool: `submit_session_events`

```
events: [...上面整理的 3-10 条...]
```

返回 `{ingested, skipped, project_id}`。如果 `skipped > 0`,说明部分 event 被 backend 去重 (content_hash 已存在),正常不用担心。

### Step 3 · 触发蒸馏 pipeline

调 MCP tool: `distill_document`

```
document_type: "<step 1 用户选的类型>"
time_window: "this_week"  // 默认; 用户明说 "上周/最近 7 天" 时改
```

返回 `{asset_id, status: "generating", view_url, estimated_seconds: 60}`。`view_url` 是完整可点击的绝对 URL (前缀由 `TOKENKNOWS_WEB_BASE` 决定,默认 `http://127.0.0.1:5173`)。

告诉用户:"已触发蒸馏,大约 60 秒。我会轮询完成状态。"

### Step 4 · 轮询完成

每 5-10 秒调一次 `get_asset(asset_id)`,直到 `status == "draft"` (或 `failed`)。

- 如果 60 秒还在 generating,告诉用户后端 LLM 还在跑,继续等
- 如果超 3 分钟 → 后端可能挂,提示用户查 backend log
- 如果 status=`draft` → 进入 Step 5

### Step 5 · 展示蒸馏结果

调 `get_asset_chapters(asset_id)`,拿到完整 markdown。

展示方式按类型分:

- **weekly_report / tech_design / adr / incident**: 把每个 chapter 的 `title` + `content` 用 markdown headings 直接输出给用户
- **book**: 章节多,先列大纲 (chapter titles) 给用户,再问要看哪几章
- **agent_skill**: 输出 SKILL.md 风格 markdown, 让用户决定是否落地到 `~/.claude/skills/`
- **knowledge_graph**: layout 含 nodes/edges; 用 ASCII art 简述 (e.g. `Alice --authored_by--> PR#127`),指引用户开浏览器看可视化 (URL 在 view_url 里,绝对 URL 可直接点)

最后给用户:
- **Web 查看 URL**: `{view_url}` (绝对 URL,浏览器打开看完整富文本 + 证据链;需登录 Web 工作台)
- **跨文档跳转**: 如果是 KG, 用 `search_entity` 查关键人物/概念在其它文档的出现

## 高级用法

### 指定 project

不传 project_id 时,会用 plugin manifest 配置的 default。如果用户在某 repo 下想用别的 project,显式传:
```
distill_document(document_type="adr", project_id="proj-other-001")
```

### 自定义时间窗

支持: `this_week` / `last_week` / `last_7_days` / `last_14_days` / `last_30_days`。

### 跨实体查询

用户问 "Alice 在哪些文档里出现过?" → 调 `search_entity(query="Alice")`,返回 entity list 含 source_refs (asset_id 列表)。

## 边界

- **不要** 自己写蒸馏内容; 永远走后端 pipeline
- **不要** 在 events.content 里塞超大代码 dump; 截短 2000 字符以内
- backend 不通 / 401 缺 token / 404 项目不存在时,MCP tool 会返回**带修复指引的双语错误信息** (含 uvicorn 启动命令 / `TOKENKNOWS_API_BASE` / token 获取路径) — **原样转述给用户即可**,不要自己编排查步骤
