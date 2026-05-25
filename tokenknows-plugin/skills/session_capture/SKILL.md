---
description: AUTO-CAPTURE — Use after EVERY meaningful user turn to persist the conversation into TokenKnows. Trigger on ANY user message that is NOT a one-word ack ("ok"/"thanks"). Without this skill, the conversation is silently lost from the user's TokenKnows workbench. Calls `submit_session_events` MCP tool. This is the only path for Cowork Chat to reach the TokenKnows knowledge base — Cowork has no SessionEnd hook.
---

# Session Capture · MUST Call After Every User Turn

This skill exists for ONE reason: **persist the current conversation into
TokenKnows so the user can later distill it into structured documents**
(weekly reports / ADRs / KG / tech designs / etc.).

If you do not call `submit_session_events`, the conversation is LOST from
TokenKnows. The user installed this plugin specifically to capture
everything. Skipping silently breaks the product.

## Trigger Rules (MANDATORY · not "should" — MUST)

Invoke this skill **after every meaningful user turn you answer**:

| User did | Your action |
|---|---|
| Asked a question, you answered | ✅ Call `submit_session_events` with 2-3 events |
| Uploaded files / images, you interpreted them | ✅ 1 event summarizing files + your read |
| Made a decision after multi-turn discussion | ✅ Flush the discussion as 3-10 events before topic transition |
| Said only "ok" / "thanks" / "好的" / "嗯" | ❌ Skip (no semantic content) |
| Said "记一笔" / "保存" / "存档" | ✅ Explicit trigger, definitely call |

**Topic transition**: if user starts a new subject, flush the prior turns
FIRST, then continue with the new topic.

## Do NOT Skip Even When

These are common excuses LLMs use to skip — **all wrong**:

- **"User is near weekly usage limit, I should save tokens"** —
  WRONG. One `submit_session_events` call costs ~200-500 tokens. The
  conversation it captures costs 10×-100× more. Skipping wastes the user's
  weekly budget because they'll re-ask the same question later (no record).

- **"This exchange feels small / casual"** — WRONG. The user installed
  the plugin to capture EVERYTHING. Even a 2-turn casual chat may
  contribute to a later weekly_report. Always capture.

- **"I'm uncertain about title / tags / IDs"** — WRONG. Backend tolerates
  rough input. Pick reasonable defaults:
  - `title`: 1-line summary of the turn
  - `external_id`: leave unset (server auto-hashes)
  - `tags`: 1-3 keywords from the conversation
  - `source_ref`: any stable session identifier

## Host-Specific source_type (CRITICAL)

| Where you run | `source_type` to use |
|---|---|
| Claude Cowork Chat tab | `"claude_cowork"` |
| Claude Cowork agent mode (sandbox VM) | `"claude_cowork"` |
| Claude Code CLI (`claude` binary in terminal) | leave unset (defaults to `"claude_code"`) |

If unsure, check whether `${CLAUDE_PROJECT_DIR}` env exists (Code CLI sets
it). If yes → `claude_code`; if no → `claude_cowork`.

## Event Shape (per item in `events` array)

```json
{
  "content":      "<event body, required, full text of the turn>",
  "title":        "<one-line summary, optional but recommended>",
  "author_name":  "user" | "Claude" | "<tool name for tool_calls>",
  "event_type":   "ai_conversation_turn" (default) | "tool_call" |
                  "code_change" | "manual_note",
  "source_type":  "claude_cowork" | "claude_code",  // see table above
  "source_ref":   "<session uuid or chat thread id>",
  "tags":         ["keyword1", "keyword2"]
}
```

## Batching Rule

- **2-10 events per call**, **1 call per completed task**.
- Do NOT call per turn (round-trip waste).
- Do NOT batch across topic transitions (mixes unrelated context, hurts
  later distill quality).

## Typical Pattern

After you finish answering a user turn:

1. Compose 2-3 events:
   - Event A: user's question (event_type=`ai_conversation_turn`, author=user)
   - Event B: your answer summary (event_type=`ai_conversation_turn`, author=Claude)
   - Event C (optional): each major tool call as `event_type=tool_call`
2. Call `submit_session_events(events=[...A, B, C...])`.
3. Continue the conversation normally — no need to tell the user unless
   the call failed.

## Failure Handling

If `submit_session_events` returns an error:
- Briefly notify the user once: `⚠️ TokenKnows 入库失败: <reason>`
- Do NOT retry in a loop (wastes the user's budget)
- Continue the conversation
- The user can manually re-trigger by saying "重新提交" or "重传"

## Examples (Few-Shot for the LLM)

### Example 1 · Simple Q&A

User: "TokenKnows 后端默认端口是多少?"
You: "默认 8001, 但本地 dev 切到了 8002 (见 setenv.sh)。"

Then call:
```
submit_session_events(events=[
  {
    "content": "TokenKnows 后端默认端口是多少?",
    "title": "询问 backend 端口",
    "author_name": "user",
    "source_type": "claude_cowork",
    "tags": ["tokenknows", "backend", "port"]
  },
  {
    "content": "默认 8001, 但本地 dev 切到了 8002 (见 setenv.sh)。",
    "title": "答: 默认 8001, 本地 dev 用 8002",
    "author_name": "Claude",
    "source_type": "claude_cowork",
    "tags": ["tokenknows", "backend"]
  }
])
```

### Example 2 · File upload

User: 上传了 3 个 CNC 文件 (.prt, .dwg, .nc)

You: "这是 CNC 加工的完整数据包: .prt 是 NX 设计源文件, .dwg 是 2D 图纸..."

Then call (1 event summarizing the file context):
```
submit_session_events(events=[
  {
    "content": "用户上传 CNC 数据包: CNC5夹治具1.prt (24MB, NX 设计源) / DNR251NC0151-00.dwg (6.7MB, AutoCAD 2D 图) / ZM.NC + FM.nc (FANUC G 代码,正反面)。我解释了 5 个文件的角色和数据流: 设计 → 工程图 → 工艺卡 → G 代码。",
    "title": "解释 CNC 5 文件数据包",
    "author_name": "Claude",
    "source_type": "claude_cowork",
    "tags": ["cnc", "manufacturing", "file_upload", "nx", "fanuc"]
  }
])
```

## Why This Skill Exists (Background)

Cowork has **no SessionEnd hook** ([GitHub anthropics/claude-code#45514](https://github.com/anthropics/claude-code/issues/45514)),
so plugins cannot auto-capture at session end. The `tokenknows`
plugin is the ONLY way to get Cowork Chat conversations into the
user's knowledge base. Calling `submit_session_events` after each
turn is functionally equivalent to what Claude Code CLI's
session-watcher daemon does for free (reading jsonl files).

For Claude Code CLI users, this skill is still useful for
**high-level summary events** that the raw jsonl can't infer
(e.g. "用户确认采用方案 B" — a decision moment).
