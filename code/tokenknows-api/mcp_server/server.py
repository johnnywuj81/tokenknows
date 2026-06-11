"""tokenknows-mcp · v2.0 T117 · MCP server (FastMCP).

为 Claude Code / Claude Cowork 等 MCP host 暴露 TokenKnows 蒸馏能力:
  - tools: submit_session_events / distill_document / list_assets /
           get_asset / get_asset_chapters / search_entity
  - resources: tokenknows://asset/{id} 让 host 直接读 asset markdown
  - prompts: 7 类蒸馏的标准 prompt 模板

启动:
    # stdio (Claude Code / Cowork 默认)
    python -m mcp_server

    # SSE (远程 / docker)
    python -m mcp_server --transport sse --port 8765

环境变量:
    TOKENKNOWS_API_BASE      backend URL (默认 http://127.0.0.1:8001)
    TOKENKNOWS_API_TOKEN     JWT bearer (可选)
    TOKENKNOWS_DEFAULT_PROJECT  当前默认 project_id
    TOKENKNOWS_WEB_BASE      web UI base URL (默认 http://127.0.0.1:5173,
                             用于拼 view_url 绝对地址)
"""

from __future__ import annotations

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from mcp_server.client import get_client

# T143 (2026-05-25) · 三改 · 改用 Anthropic Progressive Disclosure pattern.
# 详细 "MUST call" 规则搬到 skills/session_capture/SKILL.md (L2 lazy load,
# 只在 LLM 觉得 task 相关时才进 context), MCP server instructions 只留必要
# 的 host 映射 + tool 清单, tool docstring 只剩 args/return.
# 这样 startup 注入小 (节省 context), 但 LLM 调 skill 时拿到完整规则.
_MCP_INSTRUCTIONS = """\
# TokenKnows MCP

This server bridges your session into the TokenKnows knowledge base.

## Available tools

- `submit_session_events` — persist conversation turns. **See the
  `session_capture` skill in this plugin for when/how to call it.**
- `distill_document(type, project_id?, time_window?)` — trigger backend
  5-stage pipeline to produce 1 of 7 document types (weekly_report /
  tech_design / adr / incident / book / agent_skill / knowledge_graph).
  See `distill` skill for the full flow.
- `list_assets` / `get_asset` / `get_asset_chapters` — read distilled output.
- `search_entity(query, entity_type?)` — cross-document KG entity search.

## Host source_type quick map

- Cowork Chat / Cowork tab → pass `source_type="claude_cowork"`
- Claude Code CLI → leave `source_type` unset (defaults `"claude_code"`)
"""

mcp = FastMCP("tokenknows", instructions=_MCP_INSTRUCTIONS)


def _web_base() -> str:
    """获取 web UI base URL (env TOKENKNOWS_WEB_BASE > 默认本地 dev 5173), 去尾斜杠."""
    return os.getenv("TOKENKNOWS_WEB_BASE", "http://127.0.0.1:5173").rstrip("/")


def _default_project_id(override: str | None = None) -> str:
    """获取 default project_id (CLI flag > env > raise)."""
    pid = override or os.getenv("TOKENKNOWS_DEFAULT_PROJECT")
    if not pid:
        raise ValueError(
            "project_id missing; set TOKENKNOWS_DEFAULT_PROJECT or pass the "
            "project_id argument"
            " · 未指定 project_id: 设置环境变量 TOKENKNOWS_DEFAULT_PROJECT 或在"
            "命令中传入 project_id 参数."
        )
    return pid


# ── tools ────────────────────────────────────────────────────────


@mcp.tool()
async def submit_session_events(
    events: list[dict],
    project_id: str | None = None,
) -> dict:
    """Persist conversation events into TokenKnows backend.

    See the `session_capture` skill in this plugin for full call-timing
    rules and examples (lazy-loaded, ~50 tokens at startup, full body
    only when LLM determines relevance).

    Args:
        events: 1-100 events. Each item: {content (required), title?,
            author_name?, event_type? (default "ai_conversation_turn"),
            source_type? ("claude_cowork" in Cowork, default "claude_code"
            elsewhere), source_ref?, external_id? (auto-hash), tags?}.
        project_id: optional override; defaults TOKENKNOWS_DEFAULT_PROJECT.

    Returns:
        {"ingested": <new>, "skipped": <dup>, "project_id": "..."}
    """
    import hashlib
    from datetime import datetime, timezone

    pid = _default_project_id(project_id)
    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload_events = []
    for ev in events[:100]:
        content = ev.get("content", "")
        ext_id = ev.get("external_id") or hashlib.sha1(
            (ev.get("source_ref", "") + content[:200]).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:16]
        author = None
        if ev.get("author_name"):
            author = {"name": ev["author_name"]}
        payload_events.append({
            "source_type": ev.get("source_type", "claude_code"),
            "source_ref": ev.get("source_ref", "claude-session"),
            "external_id": ext_id,
            "event_type": ev.get("event_type", "ai_conversation_turn"),
            "occurred_at": ev.get("occurred_at") or now_iso,
            "author": author,
            "title": ev.get("title"),
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "tags": ev.get("tags", []),
            "trust_score": ev.get("trust_score"),
        })

    resp = await client.post(
        f"/api/v1/projects/{pid}/events",
        json={"events": payload_events},
    )
    return {
        "ingested": resp.get("ingested", 0),
        "skipped": resp.get("skipped", 0),
        "project_id": pid,
    }


@mcp.tool()
async def distill_document(
    document_type: Literal[
        "weekly_report", "tech_design", "adr", "incident",
        "book", "agent_skill", "knowledge_graph",
    ],
    project_id: str | None = None,
    time_window: str = "this_week",
    model: str | None = None,
) -> dict:
    """触发 backend 5-stage pipeline 蒸馏 events → 文档.

    Args:
        document_type: 7 类之一 (周报 / 技术方案 / ADR / 复盘 / 书籍 /
                       Skill / 知识图谱)
        project_id: 项目 id; 不传用 default
        time_window: 时间窗 (this_week/last_week/last_7_days/last_14_days/last_30_days)
        model: 显式指定 model (e.g. "claude-sonnet-4-6"); 不传走 task 默认

    Returns:
        {
          "asset_id": "...",
          "status": "generating",
          "title": "...",
          "view_url": "http://127.0.0.1:5173/projects/{pid}/documents/{aid}",
          "estimated_seconds": 60,
          "note": "可调 get_asset 轮询完成状态"
        }
    """
    pid = _default_project_id(project_id)
    client = get_client()
    payload: dict = {"type": document_type, "time_window": time_window}
    if model:
        payload["model_override"] = model
    resp = await client.post(
        f"/api/v1/projects/{pid}/assets/generate", json=payload,
    )
    aid = resp["id"]
    note = "调 get_asset(asset_id) 查完成状态; status='draft' 即可读 markdown."
    if not os.getenv("TOKENKNOWS_WEB_BASE"):
        note += (
            " view_url assumes the web UI at http://127.0.0.1:5173 "
            "(npm run dev); set TOKENKNOWS_WEB_BASE if deployed elsewhere; "
            "login required"
            " · view_url 默认假设 web UI 跑在 http://127.0.0.1:5173 "
            "(npm run dev), 部署在别处请设 TOKENKNOWS_WEB_BASE, 打开需先登录."
        )
    return {
        "asset_id": aid,
        "status": resp["status"],
        "title": resp["title"],
        "view_url": f"{_web_base()}/projects/{pid}/documents/{aid}",
        "estimated_seconds": 60,
        "note": note,
    }


@mcp.tool()
async def list_assets(
    project_id: str | None = None,
    asset_type: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict:
    """列项目下的蒸馏文档.

    Args:
        project_id: 项目 id; 不传用 default
        asset_type: 过滤 weekly_report/tech_design/.../knowledge_graph
        status: 过滤 generating/draft/in_review/approved/published
        limit: 1-100, 默认 20
    """
    pid = _default_project_id(project_id)
    params: dict = {"limit": limit}
    if asset_type:
        params["type"] = asset_type
    if status:
        params["status"] = status
    client = get_client()
    resp = await client.get(f"/api/v1/projects/{pid}/assets", params=params)
    # 精简返回: 只 id/type/title/status/metrics/kg_summary, 不带 thumbnail (太大)
    items = []
    for a in resp.get("data", []):
        item = {
            "id": a["id"],
            "type": a["type"],
            "title": a["title"],
            "status": a["status"],
            "version": a["current_version"],
            "updated_at": a["updated_at"],
        }
        if a.get("metrics"):
            item["metrics"] = a["metrics"]
        if a.get("kg_summary"):
            item["kg_summary"] = {
                "node_count": a["kg_summary"].get("node_count"),
                "edge_count": a["kg_summary"].get("edge_count"),
            }
        items.append(item)
    return {"total": resp.get("meta", {}).get("total", 0), "items": items}


@mcp.tool()
async def get_asset(asset_id: str) -> dict:
    """读单个 asset 元数据 (不含 chapter content).

    用于轮询 distill 完成状态. 完整内容用 get_asset_chapters 或读 resource.
    """
    client = get_client()
    a = await client.get(f"/api/v1/assets/{asset_id}")
    return {
        "id": a["id"],
        "type": a["type"],
        "title": a["title"],
        "status": a["status"],
        "version": a["current_version"],
        "approval_state": a["approval_state"],
        "metrics": a.get("metrics"),
        "kg_summary": a.get("kg_summary"),
        "updated_at": a["updated_at"],
    }


@mcp.tool()
async def get_asset_chapters(asset_id: str) -> list[dict]:
    """读 asset 的所有 chapter (含 markdown content + layout).

    对 knowledge_graph 类型, layout 含 nodes/edges/thumbnail_svg.
    对其它 7 类, content 是 markdown 正文.
    """
    client = get_client()
    chs = await client.get(f"/api/v1/assets/{asset_id}/chapters")
    out: list[dict] = []
    for c in chs:
        item = {
            "id": c["id"],
            "title": c["title"],
            "order_index": c["order_index"],
            "content": c["content"],
            "approval_state": c.get("approval_state", "pending"),
        }
        if c.get("layout"):
            # KG: 简化 layout 只返回结构性字段, 不返回 thumbnail (前端用)
            layout = c["layout"]
            if "nodes" in layout:
                item["kg_layout"] = {
                    "nodes": layout.get("nodes", []),
                    "edges": layout.get("edges", []),
                }
        out.append(item)
    return out


@mcp.tool()
async def search_entity(
    query: str,
    project_id: str | None = None,
    entity_type: Literal["person", "event", "concept", "artifact"] | None = None,
    min_assets: int = 1,
) -> list[dict]:
    """跨文档实体搜索 (KG entity_registry).

    例: search_entity('Alice') → 返回 Alice 出现在哪些 KG asset 里.

    Args:
        query: label / aliases 模糊匹配
        project_id: 项目 id; 不传用 default
        entity_type: 过滤 person/event/concept/artifact
        min_assets: 仅返回出现在 ≥N 个 asset 的 (跨文档实体)
    """
    pid = _default_project_id(project_id)
    params: dict = {"q": query, "min_assets": min_assets}
    if entity_type:
        params["type"] = entity_type
    client = get_client()
    entities = await client.get(
        f"/api/v1/projects/{pid}/entities", params=params,
    )
    return [
        {
            "id": e["id"],
            "type": e["type"],
            "label": e["label"],
            "aliases": e.get("aliases", []),
            "asset_count": e.get("asset_count", 0),
            "source_refs": e.get("source_refs", []),
        }
        for e in entities
    ]


# ── resources ─────────────────────────────────────────────────────


@mcp.resource("tokenknows://asset/{asset_id}")
async def asset_resource(asset_id: str) -> str:
    """以 markdown 形式读单个 asset (所有 chapter 拼接).

    Host (Claude) 可通过 @-mention 直接引用: @tokenknows://asset/demo-kg-001
    """
    client = get_client()
    asset = await client.get(f"/api/v1/assets/{asset_id}")
    chapters = await client.get(f"/api/v1/assets/{asset_id}/chapters")
    parts = [f"# {asset['title']}", "", f"_type={asset['type']} · status={asset['status']} · v{asset['current_version']}_", ""]
    for c in chapters:
        parts.extend([f"## {c['title']}", "", c.get("content", ""), ""])
    return "\n".join(parts)


# ── prompts ───────────────────────────────────────────────────────


@mcp.prompt()
def distill_session(document_type: str = "weekly_report") -> str:
    """模板: 把当前 session 蒸馏成指定文档类型.

    Args:
        document_type: weekly_report / tech_design / adr / incident / book /
                       agent_skill / knowledge_graph
    """
    return f"""请把我们这个 Claude session 的对话蒸馏成 **{document_type}** 类型文档:

1. 用 `submit_session_events` 工具把本次对话的关键节点 (用户的需求 / 你的方案 /
   关键代码变更 / 决策与权衡) 整理成 3-10 条 event 提交;
2. 调 `distill_document(document_type='{document_type}')` 触发后端流水线;
3. 用 `get_asset(asset_id)` 轮询 status (≤60s 应变 'draft');
4. 完成后用 `get_asset_chapters` 拉 markdown 给我看;
5. 如果是 knowledge_graph 类型, 用 `search_entity` 查关键人物/概念跨文档出现.
"""


# ── entry ─────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry: python -m mcp_server."""
    import argparse

    parser = argparse.ArgumentParser(description="TokenKnows MCP server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="MCP transport (stdio for Claude Code/Cowork; sse for remote)",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="SSE 端口 (仅 transport=sse 时)",
    )
    args = parser.parse_args()
    if args.transport == "sse":
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
