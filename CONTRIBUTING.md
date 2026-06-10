# Contributing to TokenKnows

> **中文导读**:欢迎贡献!环境要求 Python ≥ 3.11、Node ≥ 20,可选 Ollama(零云端 key 本地推理)。后端 `pip install -e ".[dev]"` + `pytest`,前端 `npm ci` + `npm test`。提交信息用 `type(scope): subject` 约定。代码注释以中文为主;Issue / PR 中英文皆可。

## Prerequisites

- Python ≥ 3.11
- Node.js ≥ 20
- (Optional, recommended) [Ollama](https://ollama.com) — lets the whole LLM pipeline run locally with zero cloud keys

## Setup

**Backend**

```bash
cd code/tokenknows-api
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.local.example .env.local      # defaults to Ollama
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

**Frontend**

```bash
cd code/tokenknows-web
npm ci
cp .env.local.example .env.local
npm run dev                            # http://localhost:5173
```

**Demo data** (optional): `./engineering_handoff/demo-seed.sh`

## Tests & checks (what CI runs)

```bash
# backend
cd code/tokenknows-api
PYTHONPATH=. .venv/bin/pytest tests/
.venv/bin/ruff check app/              # informational for now

# frontend
cd code/tokenknows-web
npx tsc --noEmit
npm run lint                           # strict — 0 errors required
npm test
npm run build
```

CI runs all of the above on `ubuntu-latest` for every PR ([ci.yml](.github/workflows/ci.yml)). PRs must be green before merge.

## Commit convention

`type(scope): subject` — types in use: `feat` `fix` `docs` `test` `chore` `ci` `refactor` `perf`. Scopes seen in history: `web` `api` `backend` `plugin` `distill` `auth` `brand` `oss` `dev` …

Not enforced by tooling, but please follow it for PR titles too — the history is the changelog's raw material.

## Pull request flow

1. Fork → feature branch (`feat/...`, `fix/...`)
2. Make changes; add/adjust tests for behavior changes
3. Ensure local checks above pass
4. Open a PR with the template filled in; link related issues
5. Squash-merge after CI green + review

## Language

Code comments are predominantly **Chinese** (the project's working language) — that's a convention, not an accident. English and Chinese are both welcome in issues, PRs, and discussions.

## Where things live

| Area | Path |
|---|---|
| FastAPI backend + LLM gateway | `code/tokenknows-api/` |
| React frontend | `code/tokenknows-web/` |
| Data collectors (Python) | `plugins/{claude-code,codex,cursor,github,local-docs}/` |
| VS Code extension | `plugins/vscode-tokenknows/` |
| Claude Code plugin | `tokenknows-plugin/` |
| Codex plugin (marketplace form) | `codex-plugin/` |
| macOS launchd units | `scripts/launchd/` |
| Product docs (zh) | `docs/product/` |
