#!/usr/bin/env python3
"""TokenKnows 本地文档插件 · watchdog 监听 .md / .txt / .pdf 文件入库.

设计目标:
- 监听用户指定目录 (默认 ~/Documents), 递归扫描 .md / .txt / .pdf
- 文件变更时 (created/modified): 2s 防抖, 合并连续编辑
- 删除/重命名: 暂不处理 (避免误删已入库证据)
- 投递: POST /api/v1/projects/:project_id/events, 单条/批量都走同一端点
- 幂等: content_hash 服务端去重

PDF 处理 (page-level chunking, NVIDIA benchmark 0.648 acc / 0.107 std):
- 用 pdfplumber 抽文本, CJK 支持好
- 一页 → 一条 event (source_ref = "name.pdf#page=N", payload.page = N)
- 空白页 (<30 字符) 跳过
- PDF 文件 >20MB 跳过 (parse 太慢)

trust_score 公式 (与其它插件一致):
    trust = 0.6 × authority + 0.4 × confidence
  - 本地文档是"用户主动写下"的, authority = 0.75 (高于 AI 对话, 低于代码提交)
  - confidence 按内容长度: ≥500 字符 = 1.0 / 100-500 = 0.8 / <100 = 0.5

调用:
    python3 sync.py --backend http://localhost:8001 --project proj-demo-001 \\
        --watch-dir ~/Documents/notes \\
        [--watch]       # 持续监听 (前台)
        [--bootstrap]   # 全量入库一次后退出 (适合首次启用)

依赖: stdlib + requests + watchdog (+ pdfplumber 可选, 缺则跳过 .pdf)
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

# pdfplumber 可选, 缺失时降级为只处理 .md/.txt
try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore
    _HAS_PDFPLUMBER = False

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("TK_LOG", "INFO"),
)
log = logging.getLogger("tk-local-docs")

TEXT_EXTS = {".md", ".txt"}
PDF_EXTS = {".pdf"}
ALLOWED_EXTS = TEXT_EXTS | PDF_EXTS
DEBOUNCE_SEC = 2.0
MAX_FILE_BYTES = 2 * 1024 * 1024        # 2MB; 文本类截断尾部
MAX_PDF_BYTES = 20 * 1024 * 1024        # 20MB; 超过不 parse (太慢)
MIN_PAGE_CHARS = 30                      # PDF 单页正文 < 30 字符跳过 (空白/封面)
PREVIEW_BYTES = 4096                     # content_hash 前 4KB; 防止"全文 hash 太慢"
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


def is_supported_file(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTS:
        return False
    if ext in PDF_EXTS and not _HAS_PDFPLUMBER:
        return False
    # 跳过 SKIP_DIRS 下的文件
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return False
    # 跳过点号开头隐藏文件
    if path.name.startswith("."):
        return False
    return True


# 兼容旧名 (保留 1 个 release 周期)
is_text_file = is_supported_file


def _rel_source_ref(path: Path, watch_root: Path) -> str:
    """相对路径作 source_ref. macOS /tmp → /private/tmp 需 resolve()."""
    try:
        rel = path.resolve().relative_to(watch_root.resolve())
    except ValueError:
        rel = path
    return str(rel)


def _confidence_by_length(text: str) -> float:
    if len(text) >= 500:
        return 1.0
    if len(text) >= 100:
        return 0.8
    return 0.5


def _build_event(
    *,
    path: Path,
    watch_root: Path,
    stat: os.stat_result,
    text: str,
    content_hash: str,
    title: str,
    source_ref: str,
    extension: str,
    extra_payload: dict[str, Any] | None = None,
    extra_tags: list[str] | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    """统一构造 EventCreate dict, 复用 trust_score / author / occurred_at 等."""
    occurred = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    confidence = _confidence_by_length(text)
    authority = 0.75
    trust_score = round(0.6 * authority + 0.4 * confidence, 3)

    payload: dict[str, Any] = {
        "file_path": str(path),
        "watch_root": str(watch_root),
        "size_bytes": stat.st_size,
        "truncated": truncated,
        "extension": extension,
        "trust_components": {
            "source_authority": authority,
            "extraction_confidence": confidence,
        },
    }
    if extra_payload:
        payload.update(extra_payload)

    tags = [extension.lstrip("."), "local"]
    if extra_tags:
        tags.extend(extra_tags)

    return {
        "source_type": "local_file",
        "source_ref": source_ref,
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
        "payload": payload,
        "tags": tags,
        "trust_score": trust_score,
    }


def _text_file_to_event(
    path: Path,
    watch_root: Path,
    stat: os.stat_result,
) -> dict[str, Any] | None:
    """.md / .txt → 1 条 event."""
    if stat.st_size == 0:
        return None
    try:
        raw = path.read_bytes()
    except OSError as e:
        log.warning("read %s failed: %s", path, e)
        return None

    truncated = False
    if len(raw) > MAX_FILE_BYTES:
        raw = raw[:MAX_FILE_BYTES]
        truncated = True

    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    h = hashlib.sha256()
    h.update(str(path).encode("utf-8"))
    h.update(raw[:PREVIEW_BYTES])
    content_hash = h.hexdigest()

    title = path.stem.replace("_", " ").replace("-", " ")
    title = title[:80] + "…" if len(title) > 80 else title

    return _build_event(
        path=path,
        watch_root=watch_root,
        stat=stat,
        text=text,
        content_hash=content_hash,
        title=title,
        source_ref=_rel_source_ref(path, watch_root),
        extension=path.suffix.lower(),
        truncated=truncated,
    )


def _pdf_to_events(
    path: Path,
    watch_root: Path,
    stat: os.stat_result,
) -> list[dict[str, Any]]:
    """PDF → N 条 event (一页一条, page-level chunking)."""
    if not _HAS_PDFPLUMBER:
        return []
    if stat.st_size == 0:
        return []
    if stat.st_size > MAX_PDF_BYTES:
        log.warning("pdf %s skipped: size %d > %d", path, stat.st_size, MAX_PDF_BYTES)
        return []

    base_ref = _rel_source_ref(path, watch_root)
    base_title = path.stem.replace("_", " ").replace("-", " ")

    events: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            total_pages = len(pdf.pages)
            for idx, page in enumerate(pdf.pages, start=1):
                try:
                    text = (page.extract_text() or "").strip()
                except Exception as e:  # noqa: BLE001 - pdfplumber 内部异常种类多
                    log.warning("pdf %s page %d extract failed: %s", path, idx, e)
                    continue

                if len(text) < MIN_PAGE_CHARS:
                    continue

                h = hashlib.sha256()
                h.update(str(path).encode("utf-8"))
                h.update(f"#page={idx}".encode("utf-8"))
                h.update(text[:PREVIEW_BYTES].encode("utf-8", errors="replace"))
                content_hash = h.hexdigest()

                page_label = f"p.{idx}/{total_pages}"
                title = f"{base_title} · {page_label}"
                title = title[:80] + "…" if len(title) > 80 else title

                events.append(_build_event(
                    path=path,
                    watch_root=watch_root,
                    stat=stat,
                    text=text,
                    content_hash=content_hash,
                    title=title,
                    source_ref=f"{base_ref}#page={idx}",
                    extension=".pdf",
                    extra_payload={
                        "page": idx,
                        "total_pages": total_pages,
                    },
                    extra_tags=["pdf-page"],
                ))
    except Exception as e:  # noqa: BLE001
        log.warning("pdf %s open failed: %s", path, e)
        return []
    return events


def file_to_events(
    path: Path,
    watch_root: Path,
) -> list[dict[str, Any]]:
    """读文件, 转 N 条 EventCreate dict. text=1 条, pdf=按页 N 条."""
    try:
        stat = path.stat()
    except OSError:
        return []

    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        return _pdf_to_events(path, watch_root, stat)
    ev = _text_file_to_event(path, watch_root, stat)
    return [ev] if ev else []


# 兼容旧名 (单条返回, 保留 1 个 release 周期)
def file_to_event(path: Path, watch_root: Path) -> dict[str, Any] | None:
    evs = file_to_events(path, watch_root)
    return evs[0] if evs else None


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
            if is_supported_file(p):
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
        file_events = file_to_events(p, watch_dir)
        if file_events:
            events.extend(file_events)
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
        if not is_supported_file(path):
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
            files_processed = 0
            for raw in ready:
                p = Path(raw)
                if not p.exists():
                    continue
                file_events = file_to_events(p, self.watch_root)
                if not file_events:
                    continue
                events.extend(file_events)
                files_processed += 1
                try:
                    self._state[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
            if events:
                ingested, skipped = post_events(
                    self.backend_url, self.project_id, events
                )
                log.info(
                    "flushed %d file(s), %d event(s) → ingested=%d skipped=%d",
                    files_processed, len(events), ingested, skipped,
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
    exts = sorted(TEXT_EXTS | (PDF_EXTS if _HAS_PDFPLUMBER else set()))
    pdf_note = "" if _HAS_PDFPLUMBER else " (pdfplumber 未装, .pdf 将跳过)"
    log.info("watching %s (debounce=%ds, extensions=%s)%s",
             watch_dir, int(DEBOUNCE_SEC), exts, pdf_note)
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
    # T141: default 从 env 读, 防止 plist hardcode URL 跟实际 backend 端口漂移.
    parser = argparse.ArgumentParser(description="TokenKnows local docs sync")
    parser.add_argument(
        "--backend",
        default=os.environ.get("TOKENKNOWS_API_BASE", "http://127.0.0.1:8001"),
        help="后端基址 (默认从 env TOKENKNOWS_API_BASE 读, fallback 127.0.0.1:8001)",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("TOKENKNOWS_DEFAULT_PROJECT", "proj-demo-001"),
        help="目标 project_id (默认从 env TOKENKNOWS_DEFAULT_PROJECT 读)",
    )
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
