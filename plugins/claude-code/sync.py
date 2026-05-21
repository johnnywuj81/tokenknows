#!/usr/bin/env python3
"""TokenKnows Claude Code 插件 v0 · JSONL 增量推送.

设计目标:
- 读 ~/.claude/projects/<projectDir>/<sessionId>.jsonl
- 把每个 user/assistant turn 转成 Event
- 增量: 用 ~/.tokenknows/sync_state.json 记录 (file_path, last_offset)
- 幂等: backend 用 content_hash 去重, 多次跑同一行不会重复入库
- 投递: POST /api/v1/projects/:project_id/events 批量 (≤200/批)

调用:
    python3 sync.py --backend http://localhost:8001 --project proj-demo-001 \
        [--projects-dir ~/.claude/projects] \
        [--filter-cwd /Users/wujun/TokenKnows] \
        [--watch]   # 持续模式, 默认 30s 轮询

stdin/stdout 也能跑成 cron / launchd.

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
log = logging.getLogger("tk-sync")

STATE_FILE = Path.home() / ".tokenknows" / "sync_state.json"
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
BATCH_SIZE = 200
POLL_INTERVAL_SEC = 30


# ─── State (sync_state.json) ─────────────────────────────────


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


# ─── JSONL → Event conversion ────────────────────────────────


def jsonl_entry_to_event(
    entry: dict[str, Any],
    project_id: str,
    file_path: Path,
) -> dict[str, Any] | None:
    """把单行 JSONL 转成 EventCreate dict. 不感兴趣的返回 None."""
    etype = entry.get("type")
    # 只关心真有内容的 turn (user / assistant), 跳过 queue-operation /
    # attachment / 等元数据.
    if etype not in ("user", "assistant"):
        return None

    msg = entry.get("message", {})
    role = msg.get("role")
    if role not in ("user", "assistant"):
        return None

    # content 可能是 string 或 array of blocks
    raw_content = msg.get("content", "")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    if isinstance(raw_content, str):
        text_parts.append(raw_content)
    elif isinstance(raw_content, list):
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "name": block.get("name"),
                        "input_keys": list((block.get("input") or {}).keys()),
                    }
                )
            elif btype == "tool_result":
                # 简化: tool_result 文本拼到内容
                trc = block.get("content")
                if isinstance(trc, str):
                    text_parts.append(f"[tool_result]\n{trc[:500]}")

    text = "\n".join(p for p in text_parts if p).strip()
    if not text and not tool_calls:
        return None
    if not text:
        text = f"(tool calls only: {[t['name'] for t in tool_calls]})"

    # content_hash 用于 backend 去重 (project_id + hash)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    occurred = entry.get("timestamp") or datetime.now(timezone.utc).isoformat()
    title = (text[:60] + "…") if len(text) > 60 else text
    title = title.replace("\n", " ")

    # 作者: user → 从 cwd 推断 "本人"; assistant → "Claude"
    if role == "user":
        author = {
            "name": "我",
            "email": None,
            "external_id": entry.get("userType", "external"),
        }
    else:
        # assistant
        model = msg.get("model", "claude")
        author = {"name": "Claude", "email": None, "external_id": model}

    # 事件类型: tool_use 用 tool_call, 纯文本对话用 ai_conversation_turn
    event_type = "tool_call" if tool_calls else "ai_conversation_turn"

    return {
        "source_type": "claude_code",
        "source_ref": str(file_path.parent.name),  # projectDir e.g. "-Users-wujun-TokenKnows"
        "external_id": entry.get("uuid") or f"{file_path.stem}:{occurred}",
        "version": 1,
        "event_type": event_type,
        "occurred_at": occurred,
        "author": author,
        "title": title,
        "content": text,
        "content_hash": content_hash,
        "payload": {
            "session_id": entry.get("sessionId"),
            "cwd": entry.get("cwd"),
            "git_branch": entry.get("gitBranch"),
            "version": entry.get("version"),
            "tool_calls": tool_calls,
        },
        "tags": [t for t in [entry.get("gitBranch"), role] if t],
    }


# ─── 扫描 + 投递 ─────────────────────────────────────────────


def scan_file(
    file_path: Path,
    start_offset: int,
    project_id: str,
    filter_cwd: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """读 file_path 从 start_offset 行开始, 返回 (events, new_offset)."""
    events: list[dict[str, Any]] = []
    new_offset = start_offset
    if not file_path.exists():
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
                # cwd 过滤 (只采当前项目)
                if filter_cwd and entry.get("cwd") not in (filter_cwd, None):
                    continue
                ev = jsonl_entry_to_event(entry, project_id, file_path)
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


def discover_files(projects_dir: Path) -> list[Path]:
    """所有 .jsonl 文件 (递归 1 层)."""
    return sorted(projects_dir.glob("*/*.jsonl"))


def run_once(
    projects_dir: Path,
    backend_url: str,
    project_id: str,
    filter_cwd: str | None,
) -> dict[str, int]:
    """完整跑一次扫描 + 投递. 返回 stats."""
    state = load_state()
    total_events = 0
    total_ingested = 0
    total_skipped = 0
    files_scanned = 0

    for file_path in discover_files(projects_dir):
        key = str(file_path)
        start_offset = state.get(key, 0)
        events, new_offset = scan_file(
            file_path, start_offset, project_id, filter_cwd
        )
        if events:
            ingested, skipped = post_events(backend_url, project_id, events)
            total_ingested += ingested
            total_skipped += skipped
            total_events += len(events)
            log.info(
                "scanned %s: +%d events (offset %d → %d, ingested=%d skipped=%d)",
                file_path.name, len(events), start_offset, new_offset, ingested, skipped,
            )
        state[key] = new_offset
        files_scanned += 1

    save_state(state)
    return {
        "files": files_scanned,
        "events": total_events,
        "ingested": total_ingested,
        "skipped": total_skipped,
    }


# ─── main ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="TokenKnows Claude Code sync")
    parser.add_argument("--backend", default="http://localhost:8001",
                        help="后端基址 (默认 localhost:8001)")
    parser.add_argument("--project", default="proj-demo-001",
                        help="目标 project_id")
    parser.add_argument("--projects-dir", type=Path,
                        default=DEFAULT_PROJECTS_DIR,
                        help="Claude 项目目录 (默认 ~/.claude/projects)")
    parser.add_argument("--filter-cwd",
                        help="只采 cwd 匹配的会话 (按需限制)")
    parser.add_argument("--watch", action="store_true",
                        help="持续模式, 每 30s 轮询一次")
    parser.add_argument("--reset", action="store_true",
                        help="清空 sync_state, 全量重推 (慎用)")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("state file removed, will re-ingest all")

    if not args.projects_dir.exists():
        log.error("projects dir not found: %s", args.projects_dir)
        sys.exit(1)

    log.info("backend=%s project=%s projects_dir=%s filter_cwd=%s",
             args.backend, args.project, args.projects_dir, args.filter_cwd or "(none)")

    while True:
        try:
            stats = run_once(args.projects_dir, args.backend, args.project, args.filter_cwd)
            log.info("scan done: files=%(files)d events=%(events)d "
                     "ingested=%(ingested)d skipped=%(skipped)d", stats)
        except requests.RequestException as e:
            log.error("backend unreachable: %s", e)
        if not args.watch:
            break
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
