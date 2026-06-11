# 发帖文案骨架 · 第二波

> ⚠️ **使用规则**
> - **Linux.do 明文禁止 AI 生成内容**、V2EX 社区对通稿味极其敏感、awesome-claude-code 要求人写。
>   中文帖请把下面的骨架**用你自己的话重写**（事实清单照抄没问题，叙述必须是你的声音，建议加入真实的开发挫折/取舍故事）。
> - 英文帖（HN/Reddit）可以基于草稿微调后发，但评论必须本人回，不要用 AI 生成回复。
> - 所有帖子**主动披露作者身份**；被问隐私时用 [PRIVACY-FAQ.md](PRIVACY-FAQ.md) 的标准答案。
> - Reddit 各 sub 分天发；HN 严禁拉票。

## 通用事实清单（所有帖子可复用）

- 一句话：**把 AI 编程过程蒸馏成可发布的知识资产** —— Claude Code / Codex / Cursor / VS Code 的会话自动采集，蒸馏成周报 / 技术方案 / ADR / 故障复盘 / 技术书籍 / Agent Skill / 知识图谱（7 类）
- 证据链：每条结论回链源事件（PR/对话/commit），`cosine × trust × recency` ≥2 源交叉
- 本地优先：6 个采集器全本地拉模式（无 webhook/ngrok）；LLM 默认 Ollama 全本地，云 key 走三层出域门禁 + 审计日志
- 技术栈：FastAPI + SQLite + LiteLLM / React 19 + Vite / MCP server (PyPI: `tokenknows-mcp`)
- 开源：MIT · [github.com/johnnywuj81/tokenknows](https://github.com/johnnywuj81/tokenknows)
- 安装入口：Claude Code `/plugin marketplace add johnnywuj81/tokenknows`；VS Code 市场/Open VSX 搜 TokenKnows；官方 MCP Registry `io.github.johnnywuj81/tokenknows`
- 素材：demo GIF（README 首屏）/ mp4（assets/demo/tokenknows-demo.mp4，发帖用这个）
- 自用数据背书：dogfooding 项目 8.2 万+ events、生成 40+ 文档

## V2EX · 分享创造（中文，需重写）

**标题方向**：`我做了个开源工具，把 Claude Code 的编程过程自动变成周报、ADR 和知识图谱`

**结构骨架**：
1. 痛点钩子（2-3 句你的真实经历）：和 Claude Code 结对几小时，关掉终端后那些决策/排坑过程全蒸发了；写周报还要靠回忆
2. 做了什么：一句话 + demo 动图/视频
3. 怎么工作：采集（全本地）→ 蒸馏（5-stage）→ 7 类文档 + 证据链（强调"每句话可以点开看出处"）
4. 隐私（V2EX 必问，主动先说）：自部署、零遥测、可全本地 Ollama
5. 开源信息：MIT / 不收费 / 无私域引流
6. 求反馈：最想听"你希望蒸馏出什么文档类型"
7. 真实的"踩坑花絮"加分（如 MiniMax JSON 截断、launchd env snapshot 之类真事）

## Linux.do · 开发调优（中文，必须完全自己写）

**标题**：`[开源项目] 把 Claude Code / Codex 的 session 蒸馏成周报、ADR、知识图谱 —— 自部署知识工作台`

**角度提示**（这里 Claude Code 浓度最高）：
- 开头直接说"如果你每天在 Claude Code 里泡 4 小时+，这工具是给你做的"
- 重点讲 claude-code 采集器原理（`~/.claude/projects/*.jsonl` 30s 增量轮询）—— 这个社区的人在乎实现
- `/tokenknows:weekly` `/tokenknows:adr` 等 slash 命令演示
- 发帖前确认 TL1（进 5 个主题、读 30 帖、10 分钟阅读时长）

## Show HN（英文，可微调直发）

**Title**: `Show HN: TokenKnows – Self-hosted workbench that distills AI coding sessions into docs`

**首条评论草稿**：

> Hi HN, author here. I spend most of my coding time pair-programming with Claude Code/Codex, and noticed the decisions, dead-ends and trade-offs from those sessions evaporate when the terminal closes. Weekly reports and ADRs were reconstructed from memory.
>
> TokenKnows captures those sessions locally (file watchers on `~/.claude/projects/*.jsonl` etc. — no webhooks, no cloud) and runs a 5-stage LLM pipeline that distills them into weekly reports, ADRs, incident reviews and an entity knowledge graph. Every paragraph links back to source events (PR / conversation / commit), ranked across ≥2 sources — click any claim to see the evidence.
>
> Privacy was the design constraint: collectors only talk to a backend you host; the LLM defaults to Ollama (fully local); cloud calls require a 3-layer egress gate and are audit-logged with request hashes.
>
> Stack: FastAPI + SQLite + LiteLLM, React 19, MCP server on the official registry. MIT licensed. I've been dogfooding it on its own development — 80k+ events, 40+ generated docs, including the weekly report in the demo.
>
> Things I'd love feedback on: which document types are worth distilling, and whether the evidence-linking UX earns your trust.

## Reddit r/ClaudeAI（英文，flair: Built with Claude）

**Title**: `I built a self-hosted tool that turns your Claude Code sessions into weekly reports, ADRs and a knowledge graph (MIT)`

**Body 要点**：demo GIF 开头 → what it does in 3 bullets → install (`/plugin marketplace add johnnywuj81/tokenknows`) → privacy paragraph → "author here, AMA"。
**注意**：发帖时读 sidebar 规则与 flair 列表；与 r/ChatGPTCoding 分天发。

## Reddit r/ChatGPTCoding（英文，短版）

角度差异化：**跨工具**。"Works across Claude Code / Codex / Cursor — one knowledge base for all your AI coding sessions." 其余复用 r/ClaudeAI 素材。

## 发布节奏建议

| Day | 动作 |
|---|---|
| D0 | V2EX 分享创造（晚 8-10 点）+ 即刻第一条 build-in-public |
| D1 | Linux.do 开发调优（确认 TL1 后） |
| D3 | r/ClaudeAI |
| D4 | r/ChatGPTCoding |
| D7±（周二–四 7–10am PT） | Show HN（前面反馈消化完、README/FAQ 打磨后） |
| HN 后 1-2 周 | Product Hunt |
