# 隐私答辩词 · 社区发帖必备 FAQ

> 用途：V2EX / Linux.do / r/selfhosted / r/ClaudeAI / Show HN 评论区必被拷问的问题与标准答案。
> 英文帖直接用英文版回答；所有回答基于代码现状（2026-06-11 核实），更新功能后记得同步。

## Q1 · 我的代码 / 对话会被发到哪里？

**中**：所有采集器都是本地进程（文件轮询 / 只读 SQLite / launchd），数据只发到**你自己部署的后端**（默认 `127.0.0.1:8001`）。没有 SaaS、没有我们的服务器、没有遥测。仓库里可以 grep 验证：除了你配置的 LLM provider 和 GitHub API（拉你自己的 PR），没有任何外部端点。

**EN**: All collectors are local processes (file polling / read-only SQLite / launchd). Data goes only to the backend **you** deploy (default `127.0.0.1:8001`). No SaaS, no telemetry, no third-party servers. Grep the repo: the only outbound endpoints are the LLM provider you configure and the GitHub API for your own PRs.

## Q2 · 能完全不碰云端 LLM 吗？

**中**：能。LLM 网关走 LiteLLM 多家适配，`.env.local` 默认配置就是 **Ollama**（`http://localhost:11434`）。不填任何云 key 时，整条 5-stage 蒸馏管线全本地跑，零出域。

**EN**: Yes. The LLM gateway uses LiteLLM; the default `.env.local` points at **Ollama** (`localhost:11434`). With no cloud keys set, the whole 5-stage distillation pipeline runs fully local — zero egress.

## Q3 · 如果配了云端 key（Anthropic / OpenAI / MiniMax），怎么防失控？

**中**：三层出域门禁 —— **instance ∧ project ∧ task** 三个开关全 ON 才允许一次 cloud 调用，任一 OFF 自动降级到本地模型或拒绝。每次 cloud 调用强制写 `egress_log`（请求 hash、大小、延迟、成本估算），SQLite 本地存储，有 `POST /llm/egress/preview` 可以 dry-run 看"这次会发出去什么"。

**EN**: A three-layer egress gate — **instance ∧ project ∧ task** must all be ON for any cloud call; any OFF degrades to the local model or refuses. Every cloud call is force-logged to a local `egress_log` (request hash, size, latency, cost estimate), and `POST /llm/egress/preview` dry-runs exactly what would leave the machine.

## Q4 · VS Code 扩展会上传我的源代码吗？

**中**：不会。只传文件路径 + 语言 + 行数变化 + sha256，**不传文件内容**（README 和源码都写明）。按键输入完全不采。

**EN**: No. It sends file path + language + line-count delta + sha256 only — **never file contents**. Keystrokes are not captured at all.

## Q5 · 蒸馏出来的文档可信吗？会不会幻觉？

**中**：每条结论都带证据链 —— 回链到源事件（PR/对话/commit），按 `cosine × trust × recency` 跨 ≥2 源排序；UI 里点任何段落可以看原文摘录和 TRUST/CITATION 评分。空话率/覆盖率是文档质量条的一部分，幻觉一眼可见。

**EN**: Every claim is evidence-linked back to source events (PR / conversation / commit), ranked by `cosine × trust × recency` across ≥2 sources. Click any paragraph in the UI to see the source excerpt with TRUST/CITATION scores. Coverage and fluff-rate are first-class quality metrics, so hallucinations are visible at a glance.

## Q6 · 为什么不用 webhook？

**中**：本地优先设计：全部采集器是拉模式（轮询/文件监听），不需要公网入口、不需要 ngrok、不需要把 token 给任何中间服务。

**EN**: Local-first by design: all collectors pull (polling / file watchers). No public ingress, no ngrok, no tokens handed to middleman services.

## Q7 · 数据存哪？怎么备份/删除？

**中**：单机 SQLite（`data/state.sqlite` + `data/egress.sqlite`），备份 = 拷文件，删除 = 删文件。没有云端副本。

**EN**: Single-node SQLite (`data/state.sqlite` + `data/egress.sqlite`). Backup = copy the file; delete = delete the file. No cloud copies exist.
