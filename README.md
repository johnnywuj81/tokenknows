<p align="center">
  <img src="assets/brand/png/logo-tile-512.png" alt="TokenKnows logo" width="140" />
</p>
<h1 align="center">TokenKnows</h1>
<p align="center">
  Distill AI coding sessions into living knowledge — weekly reports, ADRs,
  incident reviews, books, agent skills, and a knowledge graph.
</p>
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/johnnywuj81/tokenknows?color=d97757" alt="License"></a>
  <a href="https://github.com/johnnywuj81/tokenknows/actions/workflows/ci.yml"><img src="https://github.com/johnnywuj81/tokenknows/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Claude_Code-plugin-d97757" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/MCP-server-241b15" alt="MCP server">
  <img src="https://img.shields.io/badge/PRs-welcome-788c5d" alt="PRs welcome">
</p>
<p align="center"><b>English</b> | <a href="README.zh-CN.md">简体中文</a></p>

---

## What is TokenKnows?

You spend hours pair-programming with Claude Code, Codex, and Cursor. The decisions, bug hunts, and design trade-offs from those sessions evaporate the moment the terminal closes. TokenKnows captures them automatically and distills them into **structured, evidence-linked knowledge assets**:

**capture** (6 collectors) → **distill** (5-stage LLM pipeline) → **assets** (7 document types) → **review / redact / publish**

- 📡 **Captures everything** — Claude Code, Codex, Cursor, VS Code, GitHub PRs/commits/issues, and local docs, all via local file watchers and API polling. No webhooks, no tunnels.
- 📝 **Seven asset types** — weekly reports, tech designs, ADRs, incident reviews, long-form books, reusable agent skills (SKILL.md), and an entity knowledge graph.
- 🔗 **Evidence-linked** — every paragraph traces back to the original PR / conversation / commit, ranked by `cosine × trust × recency` across ≥2 sources.
- 🔒 **Local-first, zero egress by default** — a three-layer LLM egress gate (instance ∧ project ∧ task) with full audit logging. Pair it with Ollama and run the whole pipeline with **zero cloud keys**.

## Demo

| Workbench | Document page |
|---|---|
| [![](engineering_handoff/demo-screenshots/01-workbench.png)](engineering_handoff/demo-screenshots/01-workbench.png) | [![](engineering_handoff/demo-screenshots/04-document-page.png)](engineering_handoff/demo-screenshots/04-document-page.png) |
| **Evidence drawer** | **Publish receipt + version diff** |
| [![](engineering_handoff/demo-screenshots/05-evidence-drawer.png)](engineering_handoff/demo-screenshots/05-evidence-drawer.png) | [![](engineering_handoff/demo-screenshots/10-publish-receipt.png)](engineering_handoff/demo-screenshots/10-publish-receipt.png) |

▶ Full walkthrough: [`engineering_handoff/walkthrough.mp4`](engineering_handoff/walkthrough.mp4) (5 min, Chinese narration + subtitles)

<details>
<summary>All 12 screens</summary>

| 1 Workbench | 2 Event drawer | 3 Document list | 4 Document page |
|---|---|---|---|
| [![](engineering_handoff/demo-screenshots/01-workbench.png)](engineering_handoff/demo-screenshots/01-workbench.png) | [![](engineering_handoff/demo-screenshots/02-event-drawer.png)](engineering_handoff/demo-screenshots/02-event-drawer.png) | [![](engineering_handoff/demo-screenshots/03-document-list.png)](engineering_handoff/demo-screenshots/03-document-list.png) | [![](engineering_handoff/demo-screenshots/04-document-page.png)](engineering_handoff/demo-screenshots/04-document-page.png) |
| **5 Evidence drawer** | **6 Regenerate dialog** | **7 Review** | **8 Redaction** |
| [![](engineering_handoff/demo-screenshots/05-evidence-drawer.png)](engineering_handoff/demo-screenshots/05-evidence-drawer.png) | [![](engineering_handoff/demo-screenshots/06-regenerate-dialog.png)](engineering_handoff/demo-screenshots/06-regenerate-dialog.png) | [![](engineering_handoff/demo-screenshots/07-review-page.png)](engineering_handoff/demo-screenshots/07-review-page.png) | [![](engineering_handoff/demo-screenshots/08-redaction-page.png)](engineering_handoff/demo-screenshots/08-redaction-page.png) |
| **9 Publish dialog** | **10 Publish receipt + diff** | **11 LLM egress** | **12 Admin** |
| [![](engineering_handoff/demo-screenshots/09-publish-dialog.png)](engineering_handoff/demo-screenshots/09-publish-dialog.png) | [![](engineering_handoff/demo-screenshots/10-publish-receipt.png)](engineering_handoff/demo-screenshots/10-publish-receipt.png) | [![](engineering_handoff/demo-screenshots/11-settings-llm.png)](engineering_handoff/demo-screenshots/11-settings-llm.png) | [![](engineering_handoff/demo-screenshots/12-admin.png)](engineering_handoff/demo-screenshots/12-admin.png) |

</details>

## Install the plugin

Prerequisite: the TokenKnows backend running at `http://localhost:8001` (see Quick start), plus four exported env vars (`TOKENKNOWS_API_ROOT` / `TOKENKNOWS_API_BASE` / `TOKENKNOWS_DEFAULT_PROJECT` / `TOKENKNOWS_API_TOKEN`).

| Platform | How |
|---|---|
| **Claude Code** | `/plugin marketplace add johnnywuj81/tokenknows` → `/plugin install tokenknows@tokenknows` |
| **Codex** | `codex plugin marketplace add johnnywuj81/tokenknows` → `codex plugin add tokenknows@tokenknows` (loads skills, commands and the MCP server; local-clone alternative in [codex-plugin/README.md](codex-plugin/README.md)) |
| **Cursor** | Add the tokenknows MCP block to `~/.cursor/mcp.json` (same shape as [tokenknows-plugin/.mcp.json](tokenknows-plugin/.mcp.json)) |
| **VS Code** | Download the `.vsix` from [Releases](https://github.com/johnnywuj81/tokenknows/releases) → `code --install-extension tokenknows-vscode-*.vsix` |

The plugin gives your AI tool MCP tools (`submit_session_events`, `distill_document`, `list_assets`, `get_asset`, `get_asset_chapters`, `search_entity`) plus slash commands like `/tokenknows:weekly` and `/tokenknows:adr`.

## Quick start

```bash
# 1. (Optional but recommended) Ollama — fully local inference, zero cloud keys
ollama serve &
ollama pull minimax-m2:cloud          # or gpt-oss:20b, qwen2.5, ...

# 2. Backend (FastAPI + SQLite persistence + 3-layer LLM egress gate)
cd code/tokenknows-api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.local.example .env.local      # defaults to Ollama; edit to add cloud providers
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001

# 3. Frontend (React 19 + Vite)
cd code/tokenknows-web
npm install
npm run dev
# open http://localhost:5173 — talks to the real backend (mocks are opt-in via ?msw=1)

# (Optional) seed demo data
./engineering_handoff/demo-seed.sh
```

**Platform support**: macOS — full experience (collectors auto-start via launchd). Linux — backend, frontend, and collectors all run manually (`python3 plugins/<x>/sync.py --watch`); the launchd scripts don't apply. Windows — untested; WSL2 recommended.

## Data collectors

All local — no ngrok, no public webhooks. On macOS they restart on crash and on reboot (launchd).

| Collector | Source | Mode |
|---|---|---|
| **claude-code** | `~/.claude/projects/*.jsonl` | 30s polling, incremental offsets |
| **codex** | `~/.codex/sessions/**/rollout-*.jsonl` | 30s polling, incremental offsets |
| **cursor** | Cursor's `state.vscdb` (read-only SQLite) | 60s polling |
| **github** | GitHub REST API · PRs / issues / commits | 5min polling (`gh auth` token) |
| **vscode** | VS Code extension `onDidSaveTextDocument` | buffered, 10s flush |
| **local-docs** | `~/Documents` `.md` `.txt` `.pdf` (watchdog) | realtime, 2s debounce |

```bash
./scripts/launchd/install.sh          # macOS: install all 5 Python collectors as LaunchAgents
launchctl list | grep com.tokenknows
tail -f ~/Library/Logs/tokenknows/*.log
```

Every event carries a trust score (`0.6 × source_authority + 0.4 × extraction_confidence`); the evidence stage ranks citations by `0.6 × cosine + 0.25 × trust + 0.15 × recency` and enforces ≥2 distinct sources.

## Architecture

![Architecture overview](assets/architecture-overview.svg)

Collectors feed an event store (SQLite). A five-stage pipeline (collect → outline → content → evidence → assess) turns events into assets. The LLM Gateway unifies four providers (Anthropic / OpenAI / MiniMax / Ollama) with per-task routing and fallback chains — and refuses any cloud call unless all three egress switches are on.

## CI

| Workflow | Runner | Trigger |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | ubuntu-latest (GitHub-hosted) | push to main + every PR |
| [`ci-macos.yml`](.github/workflows/ci-macos.yml) | self-hosted macOS ARM64 | maintainer pushes to main only — never runs external PR code |

## Privacy & local-first

- Zero egress by default — cloud LLM calls require the instance **and** project **and** task switches all on
- Bring your own keys; the audit log never leaves your machine
- One-click kill switch drops the instance into fully-offline mode

Details: [PRD §6.7 data residency & egress control](docs/product/PRD_TokenKnows_MVP.md) (Chinese).

## Documentation

| Topic | Doc |
|---|---|
| Product requirements, user journeys | [PRD](docs/product/PRD_TokenKnows_MVP.md) (zh) |
| Technical design, API, schema | [TDD](docs/product/TDD_TokenKnows_MVP.md) (zh) |
| Macro architecture & milestones | [Architecture](engineering_handoff/Architecture.md) (zh) |
| Per-screen engineering decisions | [TaskTechDesign](engineering_handoff/TaskTechDesign.md) (zh) |
| Pixel-level UI mockups | [mockups/](mockups/) — open in a browser |

> Most in-depth docs are in Chinese (the project's working language). Code comments are predominantly Chinese too; issues and PRs in English or Chinese are both welcome.

## Community

[CONTRIBUTING](CONTRIBUTING.md) · [Roadmap](ROADMAP.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Security policy](SECURITY.md) · [Issues](https://github.com/johnnywuj81/tokenknows/issues)

## License

[MIT](LICENSE) © 2026 johnnywuj81
