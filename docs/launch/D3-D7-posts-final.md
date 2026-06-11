# Reddit ×2 + Show HN 直发终稿

> Reddit 被浏览器扩展安全策略拦截，需手动粘贴。两个 sub 建议隔一天发（同链接同日多发触发反垃圾）。

---

## r/ClaudeAI（flair: Built with Claude）

**Title**:

```
I built a self-hosted tool that turns your Claude Code sessions into weekly reports, ADRs and a knowledge graph (MIT)
```

**Body**:

```markdown
Author here. I spend 4-5 hours a day pair-programming with Claude Code, and kept losing the valuable part: the debugging trails, the architecture trade-offs, the "why we picked B over A". It all evaporates when the terminal closes. Weekly reports were reconstructed from memory.

All of that actually sits in `~/.claude/projects/*.jsonl` — nobody reads it. So I built a tool that does.

**TokenKnows** watches Claude Code / Codex / Cursor / VS Code / GitHub locally (pull-only: 30s incremental polling of the jsonl files, read-only access to Cursor's state.vscdb — no webhooks, no ngrok), feeds events into a backend **you** host, and runs a 5-stage LLM pipeline that distills them into weekly reports, tech designs, ADRs, incident reviews, even long-form handbooks and an entity knowledge graph.

Demo (terminal → `/tokenknows:weekly` → generated report with evidence links):
https://raw.githubusercontent.com/johnnywuj81/tokenknows/main/assets/demo/tokenknows-demo.gif

The design I care most about is **evidence-linking**: every paragraph in a distilled doc links back to its source events (which conversation, which PR, which commit), cross-ranked over ≥2 sources. The biggest problem with LLM-written reports is confident fabrication — with back-links, fabrication is visible at a glance.

Privacy, since you'll ask: collectors only talk to your own backend (FastAPI + SQLite, single file). No SaaS, no telemetry. The LLM gateway defaults to local Ollama — with no cloud keys set, the whole pipeline runs on your machine. Cloud calls (if you configure them) go through a 3-layer egress gate and are audit-logged with request hashes.

Install as a Claude Code plugin (MCP server pulled from PyPI automatically):

    /plugin marketplace add johnnywuj81/tokenknows
    /plugin install tokenknows@tokenknows

Repo (MIT): https://github.com/johnnywuj81/tokenknows

I've been dogfooding it on its own development — 80k+ events, 40+ generated docs. Honest question for this sub: what would *you* want distilled out of your sessions? There are 7 document types now, but I suspect real demand is wilder than my guesses.
```

---

## r/ChatGPTCoding（隔一天发，跨工具角度）

**Title**:

```
One knowledge base for all your AI coding sessions — works across Claude Code, Codex and Cursor (open source, self-hosted)
```

**Body**:

```markdown
Author here. If you bounce between Claude Code, Codex and Cursor like I do, your engineering context ends up scattered across three different session formats that nothing ever reads again.

I open-sourced TokenKnows: local collectors for all three (plus VS Code saves and GitHub PRs/commits/issues), one self-hosted backend, and a 5-stage LLM pipeline that distills everything into weekly reports, ADRs, incident reviews and a knowledge graph. Every claim in a generated doc links back to the source event — which session, which PR — so LLM fabrication is visible instead of hidden.

Runs fully local with Ollama (no cloud keys needed); cloud LLMs are opt-in behind an egress gate with audit logs. MIT.

Demo: https://raw.githubusercontent.com/johnnywuj81/tokenknows/main/assets/demo/tokenknows-demo.gif
Repo: https://github.com/johnnywuj81/tokenknows

Curious how others here handle this — does anyone actually mine their session logs, or is it write-only data for everyone?
```

---

## Show HN（HN 登录后可由 AI 填表，提交前再过目一眼）

**URL**: `https://github.com/johnnywuj81/tokenknows`

**Title**（80 字符内）:

```
Show HN: TokenKnows – Self-hosted workbench that distills AI coding sessions
```

**提交后立刻发的首条评论**（已在 POSTS.md，复制于此）：

```
Hi HN, author here. I spend most of my coding time pair-programming with Claude Code/Codex, and noticed the decisions, dead-ends and trade-offs from those sessions evaporate when the terminal closes. Weekly reports and ADRs were reconstructed from memory.

TokenKnows captures those sessions locally (file watchers on `~/.claude/projects/*.jsonl` etc. — no webhooks, no cloud) and runs a 5-stage LLM pipeline that distills them into weekly reports, ADRs, incident reviews and an entity knowledge graph. Every paragraph links back to source events (PR / conversation / commit), ranked across ≥2 sources — click any claim to see the evidence.

Privacy was the design constraint: collectors only talk to a backend you host; the LLM defaults to Ollama (fully local); cloud calls require a 3-layer egress gate and are audit-logged with request hashes.

Stack: FastAPI + SQLite + LiteLLM, React 19, MCP server on the official registry. MIT licensed. I've been dogfooding it on its own development — 80k+ events, 40+ generated docs, including the weekly report in the demo.

Things I'd love feedback on: which document types are worth distilling, and whether the evidence-linking UX earns your trust.
```

**纪律**：发完每条评论都本人回；绝不请人点赞；标题不加感叹号。
