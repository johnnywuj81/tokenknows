#!/usr/bin/env python3
"""TokenKnows Codex 插件 v0 · rollout JSONL 增量推送.

设计目标 (镜像 claude-code 插件, 适配 OpenAI Codex CLI/Desktop rollout 格式):
- 读 ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<ts>-<uuid>.jsonl
  (+ ~/.codex/archived_sessions/rollout-*.jsonl)
- 每个 rollout 是一次会话: 首行 session_meta (含 cwd / session id / model),
  其后 response_item (message / function_call / custom_tool_call / reasoning) +
  event_msg (运行时事件, 跳过).
- 把有内容的 turn 转成 Event:
    · message role=user/assistant  → ai_conversation_turn
    · function_call / custom_tool_call → tool_call
    · developer message / reasoning(加密) / event_msg / 注入上下文 → 跳过
- 增量: ~/.tokenknows/codex_sync_state.json 记 (file_path, last_line_offset)
- 幂等: backend 用 content_hash 去重
- 投递: POST /api/v1/projects/:project_id/events 批量 (≤200/批)

调用:
    python3 sync.py --backend http://127.0.0.1:8002 --project proj-demo-001 \
        [--sessions-dir ~/.codex/sessions] \
        [--filter-cwd /Users/wujun/TokenKnows] \
        [--include-archived] \
        [--dry-run]   # 只解析+打印统计, 不 POST (验证用)
        [--watch]     # 持续模式, 默认 30s 轮询

依赖: 仅 stdlib + requests (pip install requests).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("✗ 需安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("TK_LOG", "INFO"),
)
log = logging.getLogger("tk-codex-sync")

STATE_FILE = Path.home() / ".tokenknows" / "codex_sync_state.json"
DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
ARCHIVED_DIR = Path.home() / ".codex" / "archived_sessions"
BATCH_SIZE = 200
POLL_INTERVAL_SEC = 30

# Codex 注入到 "user" role 的非真实-用户内容前缀 (跳过, 避免污染知识库).
# 这些是 Codex CLI 自动塞进对话的上下文 / 指令, 不是用户真实输入.
_INJECTED_USER_PREFIXES = (
    "# AGENTS.md",
    "# Files mentioned by the user:",
    "<INSTRUCTIONS>",
    "<instructions>",
    "<permissions",
    "<environment_context>",
    "<user_instructions>",
    "<app-context>",
    "<editor_context>",
)

# 单条 message / tool 内容截断 (与 backend 友好; ~中文 2000 字).
_MAX_CONTENT_CHARS = 4000


# ─── State (codex_sync_state.json) ───────────────────────────


def load_state() -> dict[str, int]:
    """state = {file_path: last_line_offset}."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("state file corrupted, resetting")
        return {}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ─── session_meta (每个 rollout 首行) ────────────────────────


def read_session_meta(file_path: Path) -> dict[str, Any]:
    """读 rollout 首行 session_meta, 返回会话级上下文 (cwd / session_id / model).

    Codex rollout 首行形如:
        {"type":"session_meta","payload":{"id":..,"cwd":..,"model_provider":..,
         "originator":"Codex Desktop","cli_version":..}}
    读不到 / 首行不是 session_meta 时返回 {}.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            first = f.readline().strip()
        if not first:
            return {}
        o = json.loads(first)
        if o.get("type") != "session_meta":
            return {}
        p = o.get("payload", {}) or {}
        return {
            "session_id": p.get("id"),
            "cwd": p.get("cwd"),
            "originator": p.get("originator"),
            "model_provider": p.get("model_provider"),
            "cli_version": p.get("cli_version"),
            "source": p.get("source"),
        }
    except (OSError, json.JSONDecodeError):
        return {}


# ─── response_item → Event conversion ────────────────────────


def _extract_message_text(payload: dict[str, Any]) -> str:
    """从 message payload 抽纯文本 (content blocks 的 input_text/output_text)."""
    parts: list[str] = []
    for block in payload.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text", "text"):
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


def _is_injected_user(text: str) -> bool:
    """user message 是否是 Codex 注入的上下文 (非真实用户输入)."""
    s = text.lstrip()
    return any(s.startswith(pfx) for pfx in _INJECTED_USER_PREFIXES)


def response_item_to_event(
    payload: dict[str, Any],
    line_no: int,
    project_id: str,
    session: dict[str, Any],
) -> dict[str, Any] | None:
    """把一个 response_item.payload 转成 EventCreate dict. 不感兴趣的返回 None.

    处理:
      message role=user      → ai_conversation_turn (跳过注入上下文)
      message role=assistant → ai_conversation_turn
      message role=developer → None (系统提示)
      function_call / custom_tool_call → tool_call
      其它 (reasoning 加密 / *_output / 未知) → None
    """
    ptype = payload.get("type")
    session_id = session.get("session_id") or "unknown"
    cwd = session.get("cwd")
    model_provider = session.get("model_provider") or "openai"

    text = ""
    tool_name: str | None = None
    role: str | None = None
    event_type = "ai_conversation_turn"

    if ptype == "message":
        role = payload.get("role")
        if role == "developer":
            return None
        text = _extract_message_text(payload)
        if role == "user" and _is_injected_user(text):
            return None
        if not text:
            return None
    elif ptype in ("function_call", "custom_tool_call"):
        role = "assistant"
        event_type = "tool_call"
        tool_name = payload.get("name")
        # function_call: arguments(JSON str); custom_tool_call: input(str/patch)
        args = payload.get("arguments")
        inp = payload.get("input")
        detail = ""
        if isinstance(args, str) and args:
            detail = args
        elif inp is not None:
            detail = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False)
        text = f"[{tool_name}] {detail}".strip()
        if not text:
            return None
    else:
        # reasoning(加密) / function_call_output / custom_tool_call_output / 未知 → 跳过
        return None

    if len(text) > _MAX_CONTENT_CHARS:
        text = text[:_MAX_CONTENT_CHARS] + "…"

    content_hash = hashlib.sha256(
        f"{session_id}:{line_no}:{text}".encode("utf-8")
    ).hexdigest()

    title = (text[:60] + "…") if len(text) > 60 else text
    title = title.replace("\n", " ")

    if role == "user":
        author = {"name": "我", "email": None, "external_id": "codex_user"}
    else:
        author = {"name": "Codex", "email": None, "external_id": model_provider}

    # trust_score (mirror claude-code):
    #   assistant + tool_call = 0.85 / assistant text = 0.80 / user prompt = 0.70
    if role == "assistant" and event_type == "tool_call":
        authority = 0.85
    elif role == "assistant":
        authority = 0.80
    else:
        authority = 0.70
    if len(text) >= 50:
        confidence = 1.0
    elif len(text) >= 10:
        confidence = 0.7
    else:
        confidence = 0.4
    trust_score = round(0.6 * authority + 0.4 * confidence, 3)

    occurred = datetime.now(timezone.utc).isoformat()

    return {
        "source_type": "codex",
        "source_ref": cwd or session_id,  # 项目路径优先, 用于 evidence drawer 分组
        "external_id": f"{session_id}:{line_no}",  # 同源唯一, 行号稳定
        "version": 1,
        "event_type": event_type,
        "occurred_at": occurred,
        "author": author,
        "title": title,
        "content": text,
        "content_hash": content_hash,
        "payload": {
            "session_id": session_id,
            "cwd": cwd,
            "originator": session.get("originator"),
            "model_provider": model_provider,
            "cli_version": session.get("cli_version"),
            "tool_name": tool_name,
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": [t for t in [role, session.get("originator")] if t],
        "trust_score": trust_score,
    }


# ─── 扫描 + 投递 ─────────────────────────────────────────────


def scan_file(
    file_path: Path,
    start_offset: int,
    project_id: str,
    filter_cwd: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """读 file_path 从 start_offset 行起, 返回 (events, new_offset)."""
    events: list[dict[str, Any]] = []
    new_offset = start_offset
    if not file_path.exists():
        return events, start_offset

    session = read_session_meta(file_path)
    # 会话级 cwd 过滤 (codex cwd 在 session_meta, 不在每行)
    if filter_cwd and session.get("cwd") not in (filter_cwd, None):
        # 整个文件不匹配 → 跳过, offset 推到末尾避免重扫
        try:
            with file_path.open("r", encoding="utf-8") as f:
                total = sum(1 for _ in f)
            return events, total
        except OSError:
            return events, start_offset

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < start_offset:
                    continue
                new_offset = i + 1
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "response_item":
                    continue
                ev = response_item_to_event(
                    entry.get("payload", {}) or {}, i, project_id, session
                )
                if ev is not None:
                    events.append(ev)
    except OSError as e:
        log.warning("read %s failed: %s", file_path, e)
    return events, new_offset


def post_events(
    backend_url: str, project_id: str, events: list[dict[str, Any]]
) -> tuple[int, int]:
    """批量 POST 到 backend. 返回 (ingested, skipped)."""
    if not events:
        return 0, 0
    url = f"{backend_url.rstrip('/')}/api/v1/projects/{project_id}/events"
    ingested = 0
    skipped = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        resp = requests.post(url, json={"events": batch}, timeout=30)
        if not resp.ok:
            log.error("ingest failed: %s %s", resp.status_code, resp.text[:300])
            continue
        data = resp.json()
        ingested += data.get("ingested", 0)
        skipped += data.get("skipped", 0)
    return ingested, skipped


def discover_files(sessions_dir: Path, include_archived: bool) -> list[Path]:
    """所有 rollout-*.jsonl (sessions 下递归 YYYY/MM/DD + 可选 archived)."""
    files = list(sessions_dir.glob("**/rollout-*.jsonl"))
    if include_archived and ARCHIVED_DIR.exists():
        files += list(ARCHIVED_DIR.glob("rollout-*.jsonl"))
    return sorted(files)


def run_once(
    sessions_dir: Path,
    backend_url: str,
    project_id: str,
    filter_cwd: str | None,
    include_archived: bool,
    dry_run: bool,
) -> dict[str, int]:
    """完整跑一次扫描 + 投递 (dry_run 时只解析不投递). 返回 stats."""
    state = load_state()
    total_events = 0
    total_ingested = 0
    total_skipped = 0
    files_scanned = 0

    for file_path in discover_files(sessions_dir, include_archived):
        key = str(file_path)
        start_offset = state.get(key, 0)
        events, new_offset = scan_file(
            file_path, start_offset, project_id, filter_cwd
        )
        if events:
            if dry_run:
                total_ingested += 0
                log.info(
                    "[dry-run] %s: +%d events (offset %d → %d)",
                    file_path.name, len(events), start_offset, new_offset,
                )
            else:
                ingested, skipped = post_events(backend_url, project_id, events)
                total_ingested += ingested
                total_skipped += skipped
                log.info(
                    "scanned %s: +%d events (offset %d → %d, ingested=%d skipped=%d)",
                    file_path.name, len(events), start_offset, new_offset, ingested, skipped,
                )
            total_events += len(events)
        # dry-run 不推进 offset (方便反复验证)
        if not dry_run:
            state[key] = new_offset
        files_scanned += 1

    if not dry_run:
        save_state(state)
    return {
        "files": files_scanned,
        "events": total_events,
        "ingested": total_ingested,
        "skipped": total_skipped,
    }


# ─── main ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="TokenKnows Codex sync")
    parser.add_argument(
        "--backend",
        default=os.environ.get("TOKENKNOWS_API_BASE", "http://127.0.0.1:8002"),
        help="后端基址 (默认从 env TOKENKNOWS_API_BASE 读, fallback 127.0.0.1:8002)",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("TOKENKNOWS_DEFAULT_PROJECT", "proj-demo-001"),
        help="目标 project_id (默认从 env TOKENKNOWS_DEFAULT_PROJECT 读)",
    )
    parser.add_argument("--sessions-dir", type=Path,
                        default=DEFAULT_SESSIONS_DIR,
                        help="Codex 会话目录 (默认 ~/.codex/sessions)")
    parser.add_argument("--filter-cwd",
                        help="只采 session cwd 匹配的会话 (按需限制)")
    parser.add_argument("--include-archived", action="store_true",
                        help="也扫 ~/.codex/archived_sessions")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析+统计, 不 POST, 不推进 offset (验证用)")
    parser.add_argument("--watch", action="store_true",
                        help="持续模式, 每 30s 轮询一次")
    parser.add_argument("--reset", action="store_true",
                        help="清空 codex_sync_state, 全量重推 (慎用)")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("state file removed, will re-ingest all")

    if not args.sessions_dir.exists():
        log.error("sessions dir not found: %s", args.sessions_dir)
        sys.exit(1)

    log.info("backend=%s project=%s sessions_dir=%s filter_cwd=%s dry_run=%s",
             args.backend, args.project, args.sessions_dir,
             args.filter_cwd or "(none)", args.dry_run)

    while True:
        try:
            stats = run_once(
                args.sessions_dir, args.backend, args.project,
                args.filter_cwd, args.include_archived, args.dry_run,
            )
            log.info("scan done: files=%(files)d events=%(events)d "
                     "ingested=%(ingested)d skipped=%(skipped)d", stats)
        except requests.RequestException as e:
            log.error("backend unreachable: %s", e)
        if not args.watch:
            break
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
