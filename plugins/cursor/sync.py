#!/usr/bin/env python3
"""TokenKnows Cursor 插件 v0 · 读 SQLite cursorDiskKV → events.

Cursor 把对话存在:
    ~/Library/Application Support/Cursor/User/globalStorage/state.vscdb

里面 cursorDiskKV 表:
    key = composerData:<convId>            value = 对话元数据 (createdAt/lastUpdatedAt/
                                                   fullConversationHeadersOnly[{bubbleId,type}])
    key = bubbleId:<convId>:<bubbleId>     value = 一个 turn 的具体内容 (text/richText/context...)
    key = checkpointId:<convId>:<id>       (checkpoint, 忽略)

type=1 → user, type=2 → assistant.

调用:
    python3 plugins/cursor/sync.py
    python3 plugins/cursor/sync.py --watch          # 60s 轮询
    python3 plugins/cursor/sync.py --filter-cwd /Users/wujun/TokenKnows
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
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
log = logging.getLogger("tk-cursor-sync")

STATE_FILE = Path.home() / ".tokenknows" / "cursor_state.json"
DEFAULT_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)
BATCH_SIZE = 200
POLL_INTERVAL_SEC = 60


def load_state() -> dict[str, int]:
    """state[convId] = lastUpdatedAt_we_last_synced  (epoch ms)."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("state corrupted, reset")
        return {}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def open_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        log.error("Cursor DB not found: %s", db_path)
        sys.exit(1)
    # readonly 打开 (cursor 在跑也安全)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def list_composers(conn: sqlite3.Connection) -> list[tuple[str, dict[str, Any]]]:
    """返回 [(convId, meta_dict)]."""
    out: list[tuple[str, dict[str, Any]]] = []
    cur = conn.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    )
    for row in cur:
        key = row["key"]
        conv_id = key.split(":", 1)[1]
        try:
            meta = json.loads(row["value"])
        except json.JSONDecodeError:
            continue
        out.append((conv_id, meta))
    return out


def get_bubble(conn: sqlite3.Connection, conv_id: str, bubble_id: str) -> dict[str, Any] | None:
    key = f"bubbleId:{conv_id}:{bubble_id}"
    cur = conn.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (key,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return None


def epoch_ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bubble_to_event(
    bubble: dict[str, Any],
    conv_meta: dict[str, Any],
    conv_id: str,
    bubble_id: str,
) -> dict[str, Any] | None:
    """单 bubble → EventCreate dict."""
    btype = bubble.get("type")  # 1=user, 2=assistant
    if btype not in (1, 2):
        return None

    # 多个文本字段都可能有内容: text 是 plain, richText 是 ProseMirror JSON
    text = (bubble.get("text") or "").strip()
    if not text:
        # 退而尝试 richText 转纯文本
        rich = bubble.get("richText")
        if isinstance(rich, dict):
            text = _flatten_rich_text(rich).strip()
    if not text:
        # assistant 可能在 toolResults / suggestedCodeBlocks 里有内容
        sb = bubble.get("suggestedCodeBlocks") or []
        if sb:
            text = "(code suggestions: " + ", ".join(
                (b.get("filename") or b.get("language") or "?") for b in sb[:5]
            ) + ")"
    if not text:
        return None

    role = "user" if btype == 1 else "assistant"
    author = (
        {"name": "我", "external_id": "user"}
        if role == "user"
        else {"name": "Cursor", "external_id": "assistant"}
    )

    # Cursor 的 createdAt 是会话级, bubble 没有单独时间戳. 用会话 lastUpdatedAt 兜底.
    occurred_ms = conv_meta.get("lastUpdatedAt") or conv_meta.get("createdAt") or int(time.time() * 1000)
    occurred = epoch_ms_to_iso(occurred_ms)

    title = (text[:60] + "…") if len(text) > 60 else text
    title = title.replace("\n", " ")

    # workspace 推断
    ws_uri = conv_meta.get("workspaceRootUri") or conv_meta.get("workspaceURI") or ""
    source_ref = ws_uri.replace("file://", "") if ws_uri else conv_id[:8]

    # trust_score (0-1):
    #   source_authority:
    #     · assistant + 实质文本 = 0.80
    #     · user prompt          = 0.70
    #     · assistant + 仅代码建议 = 0.55 (没真"说话")
    #   extraction_confidence: 按文本长度
    has_real_text = bool((bubble.get("text") or "").strip())
    if role == "assistant" and has_real_text:
        authority = 0.80
    elif role == "user":
        authority = 0.70
    else:
        authority = 0.55
    if len(text) >= 50:
        confidence = 1.0
    elif len(text) >= 10:
        confidence = 0.7
    else:
        confidence = 0.4
    trust_score = round(0.6 * authority + 0.4 * confidence, 3)

    return {
        "source_type": "cursor",
        "source_ref": source_ref,
        "external_id": f"{conv_id}:{bubble_id}",
        "version": 1,
        "event_type": "ai_conversation_turn",
        "occurred_at": occurred,
        "author": author,
        "title": title,
        "content": text[:5000],
        "content_hash": _sha256(text),
        "payload": {
            "conv_id": conv_id,
            "bubble_id": bubble_id,
            "workspace": ws_uri,
            "token_count": bubble.get("tokenCount"),
            "unified_mode": conv_meta.get("unifiedMode"),
            "is_agentic": conv_meta.get("isAgentic"),
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": ["cursor", role],
        "trust_score": trust_score,
    }


def _flatten_rich_text(node: dict[str, Any]) -> str:
    """ProseMirror JSON → plain text (粗略)."""
    if not isinstance(node, dict):
        return ""
    pieces: list[str] = []
    if node.get("type") == "text":
        pieces.append(node.get("text", ""))
    for child in node.get("content", []) or []:
        pieces.append(_flatten_rich_text(child))
    return "".join(pieces)


def post_events(
    backend_url: str, project_id: str, events: list[dict[str, Any]]
) -> tuple[int, int]:
    if not events:
        return 0, 0
    url = f"{backend_url.rstrip('/')}/api/v1/projects/{project_id}/events"
    ingested = 0
    skipped = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        try:
            resp = requests.post(url, json={"events": batch}, timeout=30)
        except requests.RequestException as e:
            log.error("ingest err: %s", e)
            continue
        if not resp.ok:
            log.error("ingest fail: %d %s", resp.status_code, resp.text[:200])
            continue
        data = resp.json()
        ingested += data.get("ingested", 0)
        skipped += data.get("skipped", 0)
    return ingested, skipped


def run_once(
    db_path: Path,
    backend_url: str,
    project_id: str,
    filter_cwd: str | None,
) -> dict[str, int]:
    state = load_state()
    total = {"conversations": 0, "bubbles": 0, "events": 0, "ingested": 0, "skipped": 0}

    conn = open_db(db_path)
    try:
        composers = list_composers(conn)
        for conv_id, meta in composers:
            last_updated = meta.get("lastUpdatedAt", 0)
            # 增量: 同 convId 只在 lastUpdatedAt 推进时再扫
            if state.get(conv_id, 0) >= last_updated:
                continue
            # 项目过滤
            if filter_cwd:
                ws = meta.get("workspaceRootUri") or meta.get("workspaceURI") or ""
                ws_path = ws.replace("file://", "")
                if ws_path and not ws_path.startswith(filter_cwd):
                    state[conv_id] = last_updated
                    continue

            headers = meta.get("fullConversationHeadersOnly", []) or []
            events_for_conv: list[dict[str, Any]] = []
            for h in headers:
                bubble_id = h.get("bubbleId")
                if not bubble_id:
                    continue
                bubble = get_bubble(conn, conv_id, bubble_id)
                if bubble is None:
                    continue
                ev = bubble_to_event(bubble, meta, conv_id, bubble_id)
                if ev is not None:
                    events_for_conv.append(ev)

            if events_for_conv:
                ing, skip = post_events(backend_url, project_id, events_for_conv)
                total["events"] += len(events_for_conv)
                total["ingested"] += ing
                total["skipped"] += skip
                log.info(
                    "conv=%s bubbles=%d → events=%d ingested=%d skipped=%d",
                    conv_id[:8], len(headers), len(events_for_conv), ing, skip,
                )
            total["conversations"] += 1
            total["bubbles"] += len(headers)
            state[conv_id] = last_updated
    finally:
        conn.close()

    save_state(state)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="TokenKnows Cursor sync")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Cursor state.vscdb 路径")
    # T141: default 从 env 读 (TOKENKNOWS_API_BASE / TOKENKNOWS_DEFAULT_PROJECT)
    parser.add_argument(
        "--backend",
        default=os.environ.get("TOKENKNOWS_API_BASE", "http://127.0.0.1:8002"),
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("TOKENKNOWS_DEFAULT_PROJECT", "proj-demo-001"),
    )
    parser.add_argument("--filter-cwd",
                        help="只采 workspaceRootUri 在该路径下的对话")
    parser.add_argument("--watch", action="store_true",
                        help="持续模式 60s 轮询")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("state file removed")

    log.info("db=%s backend=%s project=%s filter_cwd=%s",
             args.db, args.backend, args.project, args.filter_cwd or "(none)")

    while True:
        try:
            stats = run_once(args.db, args.backend, args.project, args.filter_cwd)
            log.info("scan done: %s", stats)
        except sqlite3.Error as e:
            log.error("DB err: %s", e)
        except requests.RequestException as e:
            log.error("network err: %s", e)
        if not args.watch:
            break
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
