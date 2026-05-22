"""SQLite store · 单进程 cache-aside.

generation_service 用法:
    from app.persistence import get_db
    db = get_db()
    db.upsert_asset(asset_id, project_id=..., status=..., type=..., updated_at=..., json_str=...)
    db.delete_asset(asset_id)        # CASCADE 自动删 chapters/evidence/progress/...
    db.load_all_assets()             # 启动时
    ...

不暴露 sqlite3 Connection, 仅以方法暴露原子操作.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.config.logging import logger
from app.config.settings import get_settings

_db: SqliteStore | None = None
_lock = threading.Lock()


def get_db() -> SqliteStore:
    """单例 (FastAPI 单进程 + uvicorn workers=1 假设)."""
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                _db = SqliteStore.bootstrap()
    return _db


def bootstrap() -> SqliteStore:
    """显式触发. main.py startup 调."""
    return get_db()


def persist() -> SqliteStore:
    """别名, 语义对齐 'persist on mutation'."""
    return get_db()


class SqliteStore:
    """SQLite 操作封装. 注意:
    - 所有方法都自带 commit (短事务, 单语句)
    - JSON 列存 pydantic.model_dump_json()
    - 普通列从 JSON 抽出用于索引
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,  # asyncio worker 跨线程
            isolation_level=None,     # autocommit, 显式 BEGIN/COMMIT
        )
        self._conn.row_factory = sqlite3.Row
        self._write_lock = threading.RLock()

    @classmethod
    def bootstrap(cls) -> SqliteStore:
        settings = get_settings()
        # data/state.sqlite (与 egress.sqlite 同目录)
        egress_dir = Path(settings.egress_log_path).resolve().parent
        egress_dir.mkdir(parents=True, exist_ok=True)
        db_path = egress_dir / "state.sqlite"

        store = cls(db_path)
        store._apply_schema()
        logger.info("persistence_initialized", path=str(db_path))
        return store

    def _apply_schema(self) -> None:
        schema_file = Path(__file__).parent / "schema.sql"
        schema_sql = schema_file.read_text(encoding="utf-8")
        with self._write_lock:
            self._conn.executescript(schema_sql)
            self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Idempotent column-level migrations.

        SQLite 不支持 IF NOT EXISTS for ALTER ADD COLUMN, 改用 PRAGMA table_info
        探测列是否存在, 不存在再加.
        """
        # v0.2 · chapters 加 parent_id + depth + applied_skills_json
        chapter_cols = {row["name"] for row in self._query("PRAGMA table_info(chapters)")}
        if "parent_id" not in chapter_cols:
            self._exec("ALTER TABLE chapters ADD COLUMN parent_id TEXT")
        if "depth" not in chapter_cols:
            self._exec("ALTER TABLE chapters ADD COLUMN depth INTEGER DEFAULT 0")
        # 索引: book 嵌套大纲查询用 (asset_id, parent_id)
        self._exec(
            "CREATE INDEX IF NOT EXISTS chapters_parent_idx "
            "ON chapters(asset_id, parent_id)"
        )

    # ─── 通用 ──────────────────────────────────────────

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._write_lock:
            self._conn.execute(sql, params)

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    # ─── Assets ──────────────────────────────────────

    def upsert_asset(
        self,
        asset_id: str,
        project_id: str,
        status: str,
        asset_type: str,
        updated_at: str,
        json_str: str,
    ) -> None:
        self._exec(
            """
            INSERT INTO assets (id, project_id, status, type, updated_at, json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status     = excluded.status,
                type       = excluded.type,
                updated_at = excluded.updated_at,
                json       = excluded.json
            """,
            (asset_id, project_id, status, asset_type, updated_at, json_str),
        )

    def delete_asset(self, asset_id: str) -> None:
        # FK CASCADE 自动级联 chapters/evidence/progress/redaction_jobs/publish_records
        self._exec("DELETE FROM assets WHERE id = ?", (asset_id,))

    def load_all_assets(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT json FROM assets ORDER BY updated_at DESC"
        )
        return [json.loads(r["json"]) for r in rows]

    # ─── Chapters ────────────────────────────────────

    def upsert_chapter(
        self,
        chapter_id: str,
        asset_id: str,
        order_index: int,
        json_str: str,
    ) -> None:
        self._exec(
            """
            INSERT INTO chapters (id, asset_id, order_index, json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                order_index = excluded.order_index,
                json        = excluded.json
            """,
            (chapter_id, asset_id, order_index, json_str),
        )

    def replace_chapters(self, asset_id: str, chapters: list[tuple[str, int, str]]) -> None:
        """整批替换某 asset 的章节 (生成阶段一次性写入)."""
        with self._write_lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute("DELETE FROM chapters WHERE asset_id = ?", (asset_id,))
                self._conn.executemany(
                    "INSERT INTO chapters (id, asset_id, order_index, json) VALUES (?, ?, ?, ?)",
                    [(cid, asset_id, idx, j) for (cid, idx, j) in chapters],
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def load_chapters_for_asset(self, asset_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT json FROM chapters WHERE asset_id = ? ORDER BY order_index ASC",
            (asset_id,),
        )
        return [json.loads(r["json"]) for r in rows]

    # ─── Progress ────────────────────────────────────

    def upsert_progress(self, asset_id: str, overall: str, json_str: str) -> None:
        self._exec(
            """
            INSERT INTO progress (asset_id, overall, json)
            VALUES (?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                overall = excluded.overall,
                json    = excluded.json
            """,
            (asset_id, overall, json_str),
        )

    def load_progress(self, asset_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT json FROM progress WHERE asset_id = ?", (asset_id,))
        if not rows:
            return None
        return json.loads(rows[0]["json"])

    # ─── Evidence ────────────────────────────────────

    def replace_evidence(
        self, chapter_id: str, items: list[tuple[str, str]]
    ) -> None:
        """整批替换某 chapter 的 evidence."""
        with self._write_lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "DELETE FROM evidence WHERE chapter_id = ?", (chapter_id,)
                )
                self._conn.executemany(
                    "INSERT INTO evidence (id, chapter_id, json) VALUES (?, ?, ?)",
                    [(eid, chapter_id, j) for (eid, j) in items],
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def load_evidence_for_chapter(self, chapter_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT json FROM evidence WHERE chapter_id = ?", (chapter_id,)
        )
        return [json.loads(r["json"]) for r in rows]

    def load_all_evidence(self) -> dict[str, list[dict[str, Any]]]:
        """启动时全量加载. 返回 chapter_id → [evidence_dicts]."""
        rows = self._query("SELECT chapter_id, json FROM evidence")
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["chapter_id"], []).append(json.loads(r["json"]))
        return out

    # ─── Redaction jobs ──────────────────────────────

    def upsert_redaction_job(self, asset_id: str, json_str: str) -> None:
        self._exec(
            """
            INSERT INTO redaction_jobs (asset_id, json)
            VALUES (?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET json = excluded.json
            """,
            (asset_id, json_str),
        )

    def load_all_redaction_jobs(self) -> dict[str, dict[str, Any]]:
        rows = self._query("SELECT asset_id, json FROM redaction_jobs")
        return {r["asset_id"]: json.loads(r["json"]) for r in rows}

    # ─── Publish records ─────────────────────────────

    def upsert_publish_record(
        self,
        record_id: str,
        asset_id: str,
        published_at: str,
        json_str: str,
    ) -> None:
        self._exec(
            """
            INSERT INTO publish_records (id, asset_id, published_at, json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                published_at = excluded.published_at,
                json         = excluded.json
            """,
            (record_id, asset_id, published_at, json_str),
        )

    def load_all_publish_records(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT json FROM publish_records ORDER BY published_at DESC"
        )
        return [json.loads(r["json"]) for r in rows]

    # ─── Events (插件采集) ──────────────────────────────

    def upsert_event(
        self,
        event_id: str,
        project_id: str,
        source_type: str,
        event_type: str,
        occurred_at: str,
        ingested_at: str,
        content_hash: str,
        json_str: str,
    ) -> bool:
        """INSERT OR IGNORE 实现幂等. 返回 True=新增 / False=已存在."""
        with self._write_lock:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO events
                    (id, project_id, source_type, event_type, occurred_at,
                     ingested_at, content_hash, json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, project_id, source_type, event_type, occurred_at,
                 ingested_at, content_hash, json_str),
            )
            return cur.rowcount > 0

    def list_events(
        self,
        project_id: str,
        source_type: str | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """游标分页: cursor 是 occurred_at, 从该时间倒序往前.
        返回 (events_list, total_for_project_filtered).
        """
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if from_iso:
            where.append("occurred_at >= ?")
            params.append(from_iso)
        if to_iso:
            where.append("occurred_at <= ?")
            params.append(to_iso)
        # total 不含 cursor 过滤
        total_where_sql = " AND ".join(where)
        total_params = tuple(params)

        if cursor:
            where.append("occurred_at < ?")
            params.append(cursor)
        where_sql = " AND ".join(where)

        rows = self._query(
            f"""
            SELECT json FROM events
            WHERE {where_sql}
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        )
        events = [json.loads(r["json"]) for r in rows]
        total = self._query(
            f"SELECT COUNT(*) AS n FROM events WHERE {total_where_sql}",
            total_params,
        )[0]["n"]
        return events, total

    def datasource_health(
        self,
        project_id: str,
        window_days: int = 30,
    ) -> list[dict[str, Any]]:
        """每个 source_type 的健康度: 事件数 + 最近 occurred_at + 最近 ingested_at.

        语义区分:
        - event_count: 窗口内 (occurred_at) 的事件数, 反映"近期活动"
        - last_seen_at: 该源最近一次 occurred_at (历史最大值, 不受窗口限制)
        - last_ingested_at: 该源最近一次入库 ingested_at (反映插件是否仍在跑)

        e.g. Cursor 把 8 个月前的对话历史 backfill 到现在,
             event_count(30d) = 0, last_seen_at = 8个月前, last_ingested_at = 1小时前.
             前端可据此判断: "插件在跑, 但近期没有新对话".
        """
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        # 窗口内的事件统计
        in_window = self._query(
            """
            SELECT
                source_type,
                COUNT(*) AS event_count
            FROM events
            WHERE project_id = ? AND occurred_at >= ?
            GROUP BY source_type
            """,
            (project_id, cutoff),
        )
        # 历史最大时间戳 (不受窗口限制)
        all_time = self._query(
            """
            SELECT
                source_type,
                MAX(occurred_at) AS last_seen_at,
                MAX(ingested_at) AS last_ingested_at,
                COUNT(*) AS total_events
            FROM events
            WHERE project_id = ?
            GROUP BY source_type
            """,
            (project_id,),
        )
        by_type_window = {r["source_type"]: r["event_count"] for r in in_window}
        merged: list[dict[str, Any]] = []
        for r in all_time:
            st = r["source_type"]
            merged.append({
                "source_type": st,
                "event_count": by_type_window.get(st, 0),
                "total_events": r["total_events"],
                "last_seen_at": r["last_seen_at"],
                "last_ingested_at": r["last_ingested_at"],
            })
        # 按窗口内事件数降序
        merged.sort(key=lambda x: x["event_count"], reverse=True)
        return merged

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT json FROM events WHERE id = ?", (event_id,))
        if not rows:
            return None
        return json.loads(rows[0]["json"])

    # ─── Skills (v0.2 蒸馏专家技能) ─────────────────────

    def upsert_skill(
        self,
        skill_id: str,
        project_id: str,
        name: str,
        version: int,
        status: str,
        trust_score: float,
        updated_at: str,
        json_str: str,
    ) -> None:
        """新增 / 更新 skill 全字段."""
        self._exec(
            """
            INSERT INTO skills
                (id, project_id, name, version, status, trust_score, updated_at, json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name        = excluded.name,
                version     = excluded.version,
                status      = excluded.status,
                trust_score = excluded.trust_score,
                updated_at  = excluded.updated_at,
                json        = excluded.json
            """,
            (skill_id, project_id, name, version, status, trust_score,
             updated_at, json_str),
        )

    def delete_skill(self, skill_id: str) -> None:
        self._exec("DELETE FROM skills WHERE id = ?", (skill_id,))

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT json FROM skills WHERE id = ?", (skill_id,))
        if not rows:
            return None
        return json.loads(rows[0]["json"])

    def list_skills(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """按 trust_score DESC 排序; 可选按 status 过滤."""
        if status:
            rows = self._query(
                """
                SELECT json FROM skills
                WHERE project_id = ? AND status = ?
                ORDER BY trust_score DESC, updated_at DESC
                """,
                (project_id, status),
            )
        else:
            rows = self._query(
                """
                SELECT json FROM skills
                WHERE project_id = ?
                ORDER BY trust_score DESC, updated_at DESC
                """,
                (project_id,),
            )
        return [json.loads(r["json"]) for r in rows]

    def load_all_skills(self) -> list[dict[str, Any]]:
        """启动时全量加载到内存 cache."""
        rows = self._query("SELECT json FROM skills ORDER BY updated_at DESC")
        return [json.loads(r["json"]) for r in rows]

    # ─── IM Connections (v0.3 · T16) ────────────────────

    def upsert_im_connection(
        self,
        connection_id: str,
        project_id: str,
        platform: str,
        status: str,
        updated_at: str,
        json_str: str,
    ) -> None:
        """新建 / 更新 IM connection. token / consent 字段从 JSON 反序列读取."""
        self._exec(
            """
            INSERT INTO im_connections
                (id, project_id, platform, status, updated_at, json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                platform   = excluded.platform,
                status     = excluded.status,
                updated_at = excluded.updated_at,
                json       = excluded.json
            """,
            (connection_id, project_id, platform, status, updated_at, json_str),
        )

    def get_im_connection(self, connection_id: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT json FROM im_connections WHERE id = ?", (connection_id,)
        )
        if not rows:
            return None
        return json.loads(rows[0]["json"])

    def list_im_connections(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if status:
            rows = self._query(
                """
                SELECT json FROM im_connections
                WHERE project_id = ? AND status = ?
                ORDER BY updated_at DESC
                """,
                (project_id, status),
            )
        else:
            rows = self._query(
                """
                SELECT json FROM im_connections
                WHERE project_id = ?
                ORDER BY updated_at DESC
                """,
                (project_id,),
            )
        return [json.loads(r["json"]) for r in rows]

    def delete_im_connection(self, connection_id: str) -> bool:
        """级联删除 (im_messages.FK CASCADE)."""
        with self._write_lock:
            cur = self._conn.execute(
                "DELETE FROM im_connections WHERE id = ?", (connection_id,)
            )
            return cur.rowcount > 0

    def load_all_im_connections(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT json FROM im_connections ORDER BY updated_at DESC"
        )
        return [json.loads(r["json"]) for r in rows]

    # ─── IM Messages (v0.3 · T16) ────────────────────────

    def insert_im_message(
        self,
        message_id: str,
        connection_id: str,
        platform_chat_id: str,
        platform_msg_id: str,
        received_at: str,
        retention_until: str | None,
        is_signal: bool,
        redacted: bool,
        json_str: str,
    ) -> bool:
        """INSERT OR IGNORE 幂等. 返回 True=新增 / False=已存在."""
        with self._write_lock:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO im_messages
                    (id, connection_id, platform_chat_id, platform_msg_id,
                     received_at, retention_until, is_signal, redacted, json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id, connection_id, platform_chat_id, platform_msg_id,
                    received_at, retention_until,
                    1 if is_signal else 0, 1 if redacted else 0, json_str,
                ),
            )
            return cur.rowcount > 0

    def list_im_messages(
        self,
        connection_id: str,
        chat_id: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        signal_only: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        where = ["connection_id = ?"]
        params: list[Any] = [connection_id]
        if chat_id:
            where.append("platform_chat_id = ?")
            params.append(chat_id)
        if since_iso:
            where.append("received_at >= ?")
            params.append(since_iso)
        if until_iso:
            where.append("received_at <= ?")
            params.append(until_iso)
        if signal_only:
            where.append("is_signal = 1")
        where_sql = " AND ".join(where)
        rows = self._query(
            f"""
            SELECT json FROM im_messages
            WHERE {where_sql}
            ORDER BY received_at DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        )
        return [json.loads(r["json"]) for r in rows]

    def expire_im_messages(self, cutoff_iso: str) -> list[str]:
        """T22 保留期扫描: 找 retention_until <= cutoff 且未脱敏的消息 id.

        返回需要 T22 处理的消息 id 列表; 调用方负责实际脱敏后调
        mark_im_message_redacted() 标 redacted=1.
        """
        rows = self._query(
            """
            SELECT id FROM im_messages
            WHERE retention_until IS NOT NULL
              AND retention_until <= ?
              AND redacted = 0
            ORDER BY retention_until ASC
            LIMIT 500
            """,
            (cutoff_iso,),
        )
        return [r["id"] for r in rows]

    def mark_im_message_redacted(self, message_id: str, json_str: str) -> bool:
        """T22 脱敏后更新原文 + 标 redacted=1."""
        with self._write_lock:
            cur = self._conn.execute(
                """
                UPDATE im_messages SET redacted = 1, json = ?
                WHERE id = ?
                """,
                (json_str, message_id),
            )
            return cur.rowcount > 0

    # ─── ValueSegments (v0.3 · T16) ──────────────────────

    def upsert_value_segment(
        self,
        segment_id: str,
        project_id: str,
        source_type: str,
        trust_score: float,
        extracted_at: str,
        json_str: str,
    ) -> None:
        self._exec(
            """
            INSERT INTO value_segments
                (id, project_id, source_type, trust_score, extracted_at, json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_type  = excluded.source_type,
                trust_score  = excluded.trust_score,
                extracted_at = excluded.extracted_at,
                json         = excluded.json
            """,
            (segment_id, project_id, source_type, trust_score, extracted_at, json_str),
        )

    def list_value_segments(
        self,
        project_id: str,
        source_type: str | None = None,
        min_trust: float = 0.0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = ["project_id = ?", "trust_score >= ?"]
        params: list[Any] = [project_id, min_trust]
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        where_sql = " AND ".join(where)
        rows = self._query(
            f"""
            SELECT json FROM value_segments
            WHERE {where_sql}
            ORDER BY trust_score DESC, extracted_at DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        )
        return [json.loads(r["json"]) for r in rows]

    def delete_value_segment(self, segment_id: str) -> bool:
        with self._write_lock:
            cur = self._conn.execute(
                "DELETE FROM value_segments WHERE id = ?", (segment_id,)
            )
            return cur.rowcount > 0

    # ─── 调试 ────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        return {
            "assets": self._query("SELECT COUNT(*) AS n FROM assets")[0]["n"],
            "chapters": self._query("SELECT COUNT(*) AS n FROM chapters")[0]["n"],
            "evidence": self._query("SELECT COUNT(*) AS n FROM evidence")[0]["n"],
            "publish_records": self._query("SELECT COUNT(*) AS n FROM publish_records")[0]["n"],
            "events": self._query("SELECT COUNT(*) AS n FROM events")[0]["n"],
            "skills": self._query("SELECT COUNT(*) AS n FROM skills")[0]["n"],
            "im_connections": self._query("SELECT COUNT(*) AS n FROM im_connections")[0]["n"],
            "im_messages": self._query("SELECT COUNT(*) AS n FROM im_messages")[0]["n"],
            "value_segments": self._query("SELECT COUNT(*) AS n FROM value_segments")[0]["n"],
        }
