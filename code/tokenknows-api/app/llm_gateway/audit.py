"""出域审计 · 每次 cloud 调用强制记录 egress_log.

设计依据 TDD §5.4 + Pitch §5.3:
- 包含 ts / project_id / user_id / task / provider / model / sizes / tokens / latency / cost / hash_of_request
- 仅本地存储, 不上传 (私有化承诺核心)
- MVP: SQLite 文件; 生产: Postgres egress_log 表
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from app.config.settings import get_settings
from app.llm_gateway.interface import LLMMessage, LLMResponse

_init_lock = Lock()
_initialized = False


def _ensure_db() -> str:
    """惰性初始化 SQLite (建表), 返回 db 文件路径."""
    global _initialized
    settings = get_settings()
    db_path = settings.egress_log_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with _init_lock:
        if _initialized:
            return db_path
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS egress_log (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    project_id TEXT,
                    user_id TEXT,
                    task TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_size_bytes INTEGER NOT NULL,
                    response_size_bytes INTEGER NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    cost_estimate REAL NOT NULL,
                    hash_of_request TEXT NOT NULL,
                    fallback_used INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_egress_project_ts ON egress_log(project_id, ts DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_egress_provider_ts ON egress_log(provider, ts DESC)"
            )
            conn.commit()
        _initialized = True
        return db_path


@contextmanager
def _db_conn() -> Any:
    db_path = _ensure_db()
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _hash_request(messages: list[LLMMessage]) -> str:
    """SHA256 (前 16 chars) - 用于审计去重 / 不留原文."""
    payload = json.dumps(
        [{"role": m.role, "content": m.content} for m in messages],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ─── 价格表 (粗略估算, 用于 cost_estimate; T14 看板用) ─────────────
# (in_per_1m_tokens, out_per_1m_tokens) USD
PRICING: dict[str, tuple[float, float]] = {
    "anthropic": (3.0, 15.0),  # Claude Sonnet 4.5
    "openai": (2.5, 10.0),  # GPT-4o
    "minimax": (0.1, 0.3),  # MiniMax abab6.5s 估算 (¥0.01 → $0.0014 in 估算)
}


def _estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    """根据 provider + tokens 估算成本 (USD)."""
    in_price, out_price = PRICING.get(provider, (0.0, 0.0))
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


def record_egress(
    *,
    task: str,
    provider: str,
    model: str,
    messages: list[LLMMessage],
    response: LLMResponse,
    project_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    fallback_used: bool = False,
    metadata: dict | None = None,
) -> str:
    """记录一次 cloud egress. 返回 egress_log.id.

    调用时机: LLMRouter.generate() 内 cloud adapter 调用完成后强制调用.
    """
    request_size = sum(len(m.content.encode("utf-8")) for m in messages)
    response_size = len(response.text.encode("utf-8"))
    prompt_tokens = int(response.usage.get("prompt_tokens", 0))
    completion_tokens = int(response.usage.get("completion_tokens", 0))
    cost = _estimate_cost(provider, prompt_tokens, completion_tokens)
    hash_req = _hash_request(messages)

    log_id = str(uuid4())
    ts = datetime.now(UTC).isoformat()

    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO egress_log (
                id, ts, project_id, user_id, task, provider, model,
                request_size_bytes, response_size_bytes,
                prompt_tokens, completion_tokens, latency_ms,
                cost_estimate, hash_of_request, fallback_used, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                ts,
                str(project_id) if project_id else None,
                str(user_id) if user_id else None,
                task,
                provider,
                model,
                request_size,
                response_size,
                prompt_tokens,
                completion_tokens,
                response.latency_ms,
                cost,
                hash_req,
                1 if fallback_used else 0,
                json.dumps(metadata) if metadata else None,
            ),
        )
    return log_id


def list_recent_egress(limit: int = 100, project_id: str | None = None) -> list[dict]:
    """T14 出域日志面板用. 仅 admin / project owner."""
    with _db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if project_id:
            cursor.execute(
                "SELECT * FROM egress_log WHERE project_id = ? ORDER BY ts DESC LIMIT ?",
                (project_id, limit),
            )
        else:
            cursor.execute("SELECT * FROM egress_log ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_db_path() -> str:
    """供 healthcheck 探测."""
    settings = get_settings()
    return os.path.abspath(settings.egress_log_path)
