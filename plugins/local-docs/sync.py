#!/usr/bin/env python3
"""TokenKnows 本地文档插件 v0 · watchdog 监听 .md / .txt 文件入库.

设计目标:
- 监听用户指定目录 (默认 ~/Documents), 递归扫描 .md / .txt
- 文件变更时 (created/modified): 2s 防抖, 合并连续编辑
- 删除/重命名: 暂不处理 (避免误删已入库证据)
- 投递: POST /api/v1/projects/:project_id/events, 单条/批量都走同一端点
- 幂等: content_hash = sha256(file_path + mtime + size + first_4k) 服务端去重
- 初始扫描: --bootstrap 全量遍历目录并推送 (用于首次启用)

trust_score 公式 (与其它插件一致):
    trust = 0.6 × authority + 0.4 × confidence
  - 本地文档是"用户主动写下"的, authority = 0.75 (高于 AI 对话, 低于代码提交)
  - confidence 按内容长度: ≥500 字符 = 1.0 / 100-500 = 0.8 / <100 = 0.5

调用:
    python3 sync.py --backend http://localhost:8001 --project proj-demo-001 \\
        --watch-dir ~/Documents/notes \\
        [--watch]       # 持续监听 (前台)
        [--bootstrap]   # 全量入库一次后退出 (适合首次启用)

依赖: stdlib + requests + watchdog
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("✗ 需安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover
    print("✗ 需安装 watchdog: pip install watchdog", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("TK_LOG", "INFO"),
)
log = logging.getLogger("tk-local-docs")

ALLOWED_EXTS = {".md", ".txt"}
DEBOUNCE_SEC = 2.0
MAX_FILE_BYTES = 2 * 1024 * 1024   # 2MB; 超过截断尾部, 防止整个 PDF 转 md 撑爆
PREVIEW_BYTES = 4096                # content_hash 前 4KB; 防止"全文 hash 太慢"
BATCH_SIZE = 50
STATE_FILE = Path.home() / ".tokenknows" / "local_docs_state.json"

SKIP_DIRS = {
    ".git", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", ".idea", ".vscode",
    "dist", "build", "out", ".next", "target",
}


# ─── State 持久化 (last seen mtime per path) ───────────────────


def load_state() -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("state file corrupted, resetting")
        return {}


def save_state(state: dict[str, float]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ─── 文件 → Event ────────────────────────────────────────────


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() not in ALLOWED_EXTS:
        return False
    # 跳过 SKIP_DIRS 下的文件
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return False
    # 跳过点号开头隐藏文件
    if path.name.startswith("."):
        return False
    return True


def file_to_event(
    path: Path,
    watch_root: Path,
) -> dict[str, Any] | None:
    """读文件, 转 EventCreate dict. 失败返回 None."""
    try:
        stat = path.stat()
    except OSError:
        return None

    if stat.st_size == 0:
        return None

    try:
        raw = path.read_bytes()
    except OSError as e:
        log.warning("read %s failed: %s", path, e)
        return None

    # 截断超大文件
    truncated = False
    if len(raw) > MAX_FILE_BYTES:
        raw = raw[:MAX_FILE_BYTES]
        truncated = True

    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    if not text:
        return None

    # content_hash 用文件路径 + 内容前 4KB hash, 不全文是为了 watch 模式快
    h = hashlib.sha256()
    h.update(str(path).encode("utf-8"))
    h.update(raw[:PREVIEW_BYTES])
    content_hash = h.hexdigest()

    occurred = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    title = path.stem.replace("_", " ").replace("-", " ")
    title = title[:80] + "…" if len(title) > 80 else title

    # trust_score
    #   authority: 本地文档 = 0.75 (用户主动 written, 但未经验证 / 未发布)
    #   confidence: 按长度
    if len(text) >= 500:
        confidence = 1.0
    elif len(text) >= 100:
        confidence = 0.8
    else:
        confidence = 0.5
    authority = 0.75
    trust_score = round(0.6 * authority + 0.4 * confidence, 3)

    # 相对路径作 source_ref, 便于在 UI 看到"哪个文件"
    # macOS /tmp → /private/tmp symlink, 必须 resolve() 才能 relative_to
    try:
        rel = path.resolve().relative_to(watch_root.resolve())
    except ValueError:
        rel = path
    rel_str = str(rel)

    return {
        "source_type": "local_file",
        "source_ref": rel_str,
        "external_id": f"local:{content_hash[:16]}",
        "version": 1,
        "event_type": "local_document",
        "occurred_at": occurred,
        "author": {
            "name": "我",
            "email": None,
            "external_id": "local",
        },
        "title": title,
        "content": text,
        "content_hash": content_hash,
        "payload": {
            "file_path": str(path),
            "watch_root": str(watch_root),
            "size_bytes": stat.st_size,
            "truncated": truncated,
            "extension": path.suffix.lower(),
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": [
            path.suffix.lower().lstrip("."),
            "local",
        ],
        "trust_score": trust_score,
    }


# ─── 投递 ────────────────────────────────────────────────────


def post_events(
    backend_url: str,
    project_id: str,
    events: list[dict[str, Any]],
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
            log.error("ingest exception: %s", e)
            continue
        if not resp.ok:
            log.error("ingest failed: %s %s", resp.status_code, resp.text[:300])
            continue
        data = resp.json()
        ingested += data.get("ingested", 0)
        skipped += data.get("skipped", 0)
    return ingested, skipped


# ─── Bootstrap 全量扫 ────────────────────────────────────────


def discover_files(watch_dir: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(watch_dir):
        # 跳过 SKIP_DIRS
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            p = Path(root) / n
            if is_text_file(p):
                files.append(p)
    return sorted(files)


def bootstrap_scan(
    watch_dir: Path,
    backend_url: str,
    project_id: str,
) -> dict[str, int]:
    state = load_state()
    files = discover_files(watch_dir)
    log.info("bootstrap: %d files under %s", len(files), watch_dir)
    events: list[dict[str, Any]] = []
    for p in files:
        ev = file_to_event(p, watch_dir)
        if ev is not None:
            events.append(ev)
            state[str(p)] = p.stat().st_mtime
    ingested, skipped = post_events(backend_url, project_id, events)
    save_state(state)
    return {
        "files": len(files),
        "events": len(events),
        "ingested": ingested,
        "skipped": skipped,
    }


# ─── Watch 模式 (watchdog) ───────────────────────────────────


class _DocHandler(FileSystemEventHandler):
    """所有事件 → _pending[path]=now, 单独线程 2s 后批量 flush."""

    def __init__(self, watch_root: Path, backend_url: str, project_id: str) -> None:
        self.watch_root = watch_root
        self.backend_url = backend_url
        self.project_id = project_id
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._state = load_state()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._enqueue(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        # 新路径当 created 处理 (旧路径已入库, 不主动撤回)
        if event.is_directory:
            return
        self._enqueue(event.dest_path)

    def _enqueue(self, raw_path: str) -> None:
        path = Path(raw_path)
        if not is_text_file(path):
            return
        with self._lock:
            self._pending[str(path)] = time.time()

    def flush_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.5)
            now = time.time()
            ready: list[str] = []
            with self._lock:
                for p, ts in list(self._pending.items()):
                    if now - ts >= DEBOUNCE_SEC:
                        ready.append(p)
                        del self._pending[p]
            if not ready:
                continue
            events: list[dict[str, Any]] = []
            for raw in ready:
                p = Path(raw)
                if not p.exists():
                    continue
                ev = file_to_event(p, self.watch_root)
                if ev is None:
                    continue
                events.append(ev)
                try:
                    self._state[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
            if events:
                ingested, skipped = post_events(
                    self.backend_url, self.project_id, events
                )
                log.info(
                    "flushed %d file(s) → ingested=%d skipped=%d",
                    len(events), ingested, skipped,
                )
                save_state(self._state)

    def stop(self) -> None:
        self._stop.set()


def run_watch(
    watch_dir: Path,
    backend_url: str,
    project_id: str,
) -> None:
    handler = _DocHandler(watch_dir, backend_url, project_id)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=True)
    observer.start()
    flush_thread = threading.Thread(target=handler.flush_loop, daemon=True)
    flush_thread.start()
    log.info("watching %s (debounce=%ds, extensions=%s)",
             watch_dir, int(DEBOUNCE_SEC), sorted(ALLOWED_EXTS))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("stop signal received")
    finally:
        handler.stop()
        observer.stop()
        observer.join(timeout=5)


# ─── main ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="TokenKnows local docs sync")
    parser.add_argument("--backend", default="http://localhost:8001",
                        help="后端基址 (默认 localhost:8001)")
    parser.add_argument("--project", default="proj-demo-001",
                        help="目标 project_id")
    parser.add_argument("--watch-dir", type=Path,
                        default=Path.home() / "Documents",
                        help="监听目录 (默认 ~/Documents)")
    parser.add_argument("--watch", action="store_true",
                        help="持续监听模式 (watchdog)")
    parser.add_argument("--bootstrap", action="store_true",
                        help="全量扫描入库一次后退出")
    parser.add_argument("--reset", action="store_true",
                        help="清空 local_docs_state.json")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("state reset")

    if not args.watch_dir.exists():
        log.error("watch dir not found: %s", args.watch_dir)
        sys.exit(1)

    log.info("backend=%s project=%s watch_dir=%s",
             args.backend, args.project, args.watch_dir)

    if args.bootstrap or not args.watch:
        stats = bootstrap_scan(args.watch_dir, args.backend, args.project)
        log.info("bootstrap done: files=%(files)d events=%(events)d "
                 "ingested=%(ingested)d skipped=%(skipped)d", stats)
        if not args.watch:
            return

    # watch mode
    run_watch(args.watch_dir, args.backend, args.project)


if __name__ == "__main__":
    main()
