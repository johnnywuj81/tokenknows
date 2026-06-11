# TokenKnows MCP Server

<!-- mcp-name: io.github.johnnywuj81/tokenknows -->

MCP server for [TokenKnows](https://github.com/johnnywuj81/tokenknows) — a self-hosted engineering knowledge workbench that captures AI coding sessions (Claude Code / Codex / Cursor / VS Code) and distills them into structured documents: weekly reports, tech designs, ADRs, incident reviews, long-form books, agent skills and a knowledge graph, via a 5-stage LLM pipeline. Evidence-linked: every distilled claim links back to source session events.

## Prerequisites

This server is the bridge between your MCP host and a **self-hosted TokenKnows backend** (default `http://127.0.0.1:8001`). Deploy the backend first — see the [main repository](https://github.com/johnnywuj81/tokenknows). Local-first: your data goes only to the backend you configure.

The distilled documents are best viewed in the **TokenKnows web UI** (default `http://127.0.0.1:5173`, `code/tokenknows-web` in the main repo) — `view_url` links returned by the tools point there and require a logged-in session. To authenticate the MCP server against a protected backend, create an API token in the web UI under **项目设置 → MCP 接入** (Project Settings → MCP Access) and set it as `TOKENKNOWS_API_TOKEN`.

## Install & run

```bash
# Run directly (stdio, for Claude Code / Cowork / Cursor)
uvx tokenknows-mcp

# Or install then run
pip install tokenknows-mcp
tokenknows-mcp

# SSE transport for remote / docker setups
tokenknows-mcp --transport sse --port 8765
```

### Claude Code config example

```json
{
  "mcpServers": {
    "tokenknows": {
      "command": "uvx",
      "args": ["tokenknows-mcp==0.3.0"],
      "env": {
        "TOKENKNOWS_API_BASE": "${TOKENKNOWS_API_BASE:-http://127.0.0.1:8001}",
        "TOKENKNOWS_API_TOKEN": "${TOKENKNOWS_API_TOKEN:-}",
        "TOKENKNOWS_DEFAULT_PROJECT": "${TOKENKNOWS_DEFAULT_PROJECT:-proj-demo-001}",
        "TOKENKNOWS_WEB_BASE": "${TOKENKNOWS_WEB_BASE:-http://127.0.0.1:5173}"
      }
    }
  }
}
```

All values have working defaults for a default local deployment — zero exports needed. (Claude Code officially supports `${VAR:-default}` expansion in `.mcp.json`; for hosts that don't, write literal values.)

Tip: in Claude Code you can instead install the full plugin (MCP server + slash commands + skills): `/plugin marketplace add johnnywuj81/tokenknows` → `/plugin install tokenknows@tokenknows`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TOKENKNOWS_API_BASE` | `http://127.0.0.1:8001` | Self-hosted TokenKnows backend URL |
| `TOKENKNOWS_API_TOKEN` | — | API token (`tkk_...`) or JWT bearer; create in web UI → 项目设置 → MCP 接入. Optional for default local deployments |
| `TOKENKNOWS_DEFAULT_PROJECT` | `proj-demo-001` | Default project_id for event submission and distill |
| `TOKENKNOWS_WEB_BASE` | `http://127.0.0.1:5173` | Web UI base used to build `view_url` links (login required to open them) |

## Tools

- `submit_session_events` — persist conversation turns into the knowledge base
- `distill_document` — trigger the 5-stage pipeline (weekly_report / tech_design / adr / incident / book / agent_skill / knowledge_graph)
- `list_assets` / `get_asset` / `get_asset_chapters` — read distilled output
- `search_entity` — cross-document knowledge-graph entity search

Plus `tokenknows://asset/{id}` resources and prompt templates for all 7 document types.

## Session watcher (daemon)

The package also ships `tokenknows-watcher`, a standalone session watcher for Claude Code: it tails `~/.claude/projects/*.jsonl`, incrementally uploads conversation turns as events (deduped by content hash, state kept in `~/.tokenknows-watcher.json`), so `/tokenknows:weekly` always has material without manual `submit_session_events` calls.

```bash
# foreground, poll every 30s (default)
uvx --from tokenknows-mcp tokenknows-watcher

# custom interval / one-shot for cron
uvx --from tokenknows-mcp tokenknows-watcher --interval 60
uvx --from tokenknows-mcp tokenknows-watcher --once
```

It reads the same `TOKENKNOWS_API_BASE` / `TOKENKNOWS_API_TOKEN` / `TOKENKNOWS_DEFAULT_PROJECT` environment variables.

## License

[MIT](https://github.com/johnnywuj81/tokenknows/blob/main/LICENSE) — source of truth for this package lives in [`code/tokenknows-api/mcp_server`](https://github.com/johnnywuj81/tokenknows/tree/main/code/tokenknows-api/mcp_server).
