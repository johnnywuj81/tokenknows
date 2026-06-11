# TokenKnows MCP Server

<!-- mcp-name: io.github.johnnywuj81/tokenknows -->

MCP server for [TokenKnows](https://github.com/johnnywuj81/tokenknows) — a self-hosted engineering knowledge workbench that captures AI coding sessions (Claude Code / Codex / Cursor / VS Code) and distills them into structured documents: weekly reports, tech designs, ADRs, incident reviews, long-form books, agent skills and a knowledge graph, via a 5-stage LLM pipeline. Evidence-linked: every distilled claim links back to source session events.

## Prerequisites

This server is the bridge between your MCP host and a **self-hosted TokenKnows backend** (default `http://127.0.0.1:8001`). Deploy the backend first — see the [main repository](https://github.com/johnnywuj81/tokenknows). Local-first: your data goes only to the backend you configure.

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
      "args": ["tokenknows-mcp"],
      "env": { "TOKENKNOWS_API_BASE": "http://127.0.0.1:8001" }
    }
  }
}
```

Tip: in Claude Code you can instead install the full plugin (MCP server + slash commands + skills): `/plugin marketplace add johnnywuj81/tokenknows` → `/plugin install tokenknows@tokenknows`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TOKENKNOWS_API_BASE` | `http://127.0.0.1:8001` | Self-hosted TokenKnows backend URL |
| `TOKENKNOWS_API_TOKEN` | — | JWT bearer token (optional) |
| `TOKENKNOWS_DEFAULT_PROJECT` | — | Default project_id for event submission |

## Tools

- `submit_session_events` — persist conversation turns into the knowledge base
- `distill_document` — trigger the 5-stage pipeline (weekly_report / tech_design / adr / incident / book / agent_skill / knowledge_graph)
- `list_assets` / `get_asset` / `get_asset_chapters` — read distilled output
- `search_entity` — cross-document knowledge-graph entity search

Plus `tokenknows://asset/{id}` resources and prompt templates for all 7 document types.

## License

[MIT](https://github.com/johnnywuj81/tokenknows/blob/main/LICENSE) — source of truth for this package lives in [`code/tokenknows-api/mcp_server`](https://github.com/johnnywuj81/tokenknows/tree/main/code/tokenknows-api/mcp_server).
