"""v2.0 T118 · session-watcher daemon.

后台监听 ~/.claude/projects/*/sessions/*.jsonl, 增量解析新 line → 上报 events
到 tokenknows-api backend. 配合 MCP server 形成"会话即素材"的双轨:

  - 用户主动 /tokenknows:weekly  → MCP 同步蒸馏 (T117)
  - 后台 daemon 持续累积 events → 等用户随时蒸馏 (T118)

启动:
    python -m mcp_server.daemon                # 默认 poll 30s
    python -m mcp_server.daemon --interval 60  # 自定义
    python -m mcp_server.daemon --once         # 只跑一次 (cron 模式)

State 文件: ~/.tokenknows-watcher.json
  { "files": { "<jsonl_path>": { "offset": <byte_offset>, "session_id": "..." } } }

dedup: external_id = f"{session_id}-{line_no}", backend 按 content_hash 去重.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

from mcp_server.client import TokenKnowsClient


logger = logging.getLogger("tokenknows-watcher")

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_STATE_FILE = Path.home() / ".tokenknows-watcher.json"
DEFAULT_POLL_INTERVAL = 30
DEFAULT_BATCH_SIZE = 50

# 仅处理这两种 type (其它如 attachment/queue-operation/system 是 noise)
_VALID_TYPES = {"user", "assistant"}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("state file corrupt, resetting: %s", e)
        return {"files": {}}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _extract_text(message: dict) -> str:
    """提取 message.content 文本 (content 可能是 str 或 list of blocks)."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, dict):
                # text block
                if blk.get("type") == "text":
                    parts.append(blk.get("text", ""))
                # tool_use block - 不入正文, 但记其名字
                elif blk.get("type") == "tool_use":
                    name = blk.get("name", "?")
                    parts.append(f"[tool_use: {name}]")
                # tool_result - 截短
                elif blk.get("type") == "tool_result":
                    res = blk.get("content", "")
                    if isinstance(res, list):
                        res = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in res
                        )
                    parts.append(f"[tool_result: {str(res)[:200]}]")
            else:
                parts.append(str(blk))
        return "\n".join(p for p in parts if p)
    return str(content)


def _build_event(
    record: dict, session_id: str, line_no: int,
) -> dict[str, Any] | None:
    """从 jsonl 一条记录构造 EventCreate dict; None 表示跳过 (不感兴趣的 type)."""
    rec_type = record.get("type")
    if rec_type not in _VALID_TYPES:
        return None

    message = record.get("message", {})
    text = _extract_text(message)
    if not text or len(text.strip()) < 5:  # 太短无意义
        return None

    role = message.get("role", rec_type)
    timestamp = record.get("timestamp") or message.get("created_at")
    # external_id 用 session + msg uuid 或 line_no 兜底
    msg_uuid = message.get("id") or record.get("uuid") or f"line-{line_no}"
    external_id = f"{session_id}-{msg_uuid}"

    title = text.strip().splitlines()[0][:60]
    return {
        "source_type": "claude_code",
        "source_ref": session_id,
        "external_id": external_id,
        "event_type": "ai_conversation_turn",
        "occurred_at": timestamp,
        "author": {"name": "user" if role == "user" else "Claude"},
        "title": title,
        "content": text[:4000],  # backend 限 8K; 留 buffer
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "tags": ["claude-code-session", role],
        "trust_score": 0.8 if role == "user" else 0.6,
    }


def _scan_files(projects_dir: Path) -> list[Path]:
    """枚举所有 jsonl session 文件."""
    if not projects_dir.exists():
        return []
    out: list[Path] = []
    for sub in projects_dir.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.glob("*.jsonl"):
            out.append(f)
    return sorted(out)


def _session_id_from_path(p: Path) -> str:
    """jsonl 文件名 (去 .jsonl 后缀) 即 session_id."""
    return p.stem


async def _flush_batch(
    client: TokenKnowsClient, project_id: str, events: list[dict],
) -> tuple[int, int]:
    """批量上报 events 到 backend. 返回 (ingested, skipped)."""
    if not events:
        return 0, 0
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/events",
            json={"events": events},
        )
        return resp.get("ingested", 0), resp.get("skipped", 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("ingest failed (will retry next tick): %s", e)
        return 0, 0


async def _scan_once(
    client: TokenKnowsClient,
    project_id: str,
    projects_dir: Path,
    state_file: Path,
    batch_size: int,
) -> dict[str, int]:
    """扫一轮: 每个 jsonl 文件从 last_offset 起读新 line, 提交."""
    state = _load_state(state_file)
    files_state: dict[str, Any] = state.setdefault("files", {})

    total_ingested = 0
    total_skipped = 0
    total_lines = 0

    for jsonl in _scan_files(projects_dir):
        key = str(jsonl)
        entry = files_state.setdefault(key, {"offset": 0, "session_id": _session_id_from_path(jsonl)})
        try:
            size = jsonl.stat().st_size
        except OSError:
            continue
        if size <= entry["offset"]:
            continue  # 无新增

        # 读新 line
        try:
            with jsonl.open("rb") as f:
                f.seek(entry["offset"])
                new_blob = f.read()
            new_text = new_blob.decode("utf-8", errors="ignore")
        except OSError as e:
            logger.warning("read %s failed: %s", jsonl, e)
            continue

        session_id = entry["session_id"]
        batch: list[dict] = []
        last_complete_offset = entry["offset"]
        cursor_in_blob = 0
        for line in new_text.splitlines(keepends=True):
            # 不处理不完整的最后一行 (没换行符 → 还在写)
            if not line.endswith("\n"):
                break
            cursor_in_blob += len(line.encode("utf-8"))
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_lines += 1
            line_no = record.get("line_no", 0)  # 没有就 0, 不影响 dedup
            ev = _build_event(record, session_id, line_no)
            if ev:
                batch.append(ev)
            if len(batch) >= batch_size:
                ing, skp = await _flush_batch(client, project_id, batch)
                total_ingested += ing
                total_skipped += skp
                batch.clear()
                # 推进 offset (按已处理 byte)
                last_complete_offset = entry["offset"] + cursor_in_blob

        # flush 尾批
        if batch:
            ing, skp = await _flush_batch(client, project_id, batch)
            total_ingested += ing
            total_skipped += skp
            last_complete_offset = entry["offset"] + cursor_in_blob

        entry["offset"] = last_complete_offset
        files_state[key] = entry

    state["files"] = files_state
    _save_state(state_file, state)
    return {
        "lines": total_lines,
        "ingested": total_ingested,
        "skipped": total_skipped,
    }


async def _run_loop(args: argparse.Namespace) -> None:
    client = TokenKnowsClient()
    project_id = os.getenv("TOKENKNOWS_DEFAULT_PROJECT")
    if not project_id:
        logger.error("TOKENKNOWS_DEFAULT_PROJECT 未设置, 退出")
        sys.exit(2)

    projects_dir = Path(args.projects_dir)
    state_file = Path(args.state_file)
    interval = args.interval
    batch = args.batch_size

    logger.info(
        "watcher started: project=%s projects_dir=%s state=%s interval=%ds",
        project_id, projects_dir, state_file, interval,
    )

    # SIGTERM/SIGINT 平滑退出
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # windows
            pass

    while not stop_event.is_set():
        try:
            stats = await _scan_once(
                client, project_id, projects_dir, state_file, batch,
            )
            if stats["lines"] > 0:
                logger.info(
                    "scan tick · lines=%d ingested=%d skipped=%d",
                    stats["lines"], stats["ingested"], stats["skipped"],
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("scan tick failed: %s", e)

        if args.once:
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    logger.info("watcher stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="tokenknows session watcher")
    parser.add_argument(
        "--projects-dir", default=str(DEFAULT_PROJECTS_DIR),
        help="Claude Code 项目目录 (默认 ~/.claude/projects)",
    )
    parser.add_argument(
        "--state-file", default=str(DEFAULT_STATE_FILE),
        help="watcher state json 路径 (默认 ~/.tokenknows-watcher.json)",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_POLL_INTERVAL,
        help=f"轮询间隔秒 (默认 {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"单批最大 events (默认 {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只跑一次扫描就退出 (cron 模式)",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        asyncio.run(_run_loop(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
