-- TokenKnows 应用状态持久化 · SQLite
-- 单文件 data/state.sqlite. JSON 列存 pydantic dump.
-- 普通列拿出来仅供索引/外键查询.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS assets (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    status      TEXT NOT NULL,
    type        TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    json        TEXT NOT NULL          -- 完整 Asset dump
);
CREATE INDEX IF NOT EXISTS assets_project_idx ON assets(project_id);
CREATE INDEX IF NOT EXISTS assets_updated_idx ON assets(updated_at DESC);

CREATE TABLE IF NOT EXISTS chapters (
    id          TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    json        TEXT NOT NULL,         -- 完整 Chapter dump
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chapters_asset_idx ON chapters(asset_id, order_index);

CREATE TABLE IF NOT EXISTS progress (
    asset_id    TEXT PRIMARY KEY,
    overall     TEXT NOT NULL,
    json        TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    id          TEXT PRIMARY KEY,
    chapter_id  TEXT NOT NULL,
    json        TEXT NOT NULL,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS evidence_chapter_idx ON evidence(chapter_id);

CREATE TABLE IF NOT EXISTS redaction_jobs (
    asset_id    TEXT PRIMARY KEY,
    json        TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publish_records (
    id              TEXT PRIMARY KEY,
    asset_id        TEXT NOT NULL,
    published_at    TEXT NOT NULL,
    json            TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS publish_records_asset_idx ON publish_records(asset_id, published_at DESC);

-- Events · 插件采集的研发事件 (PRD §7.2.1)
-- content_hash 唯一索引保 ingest 幂等
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    occurred_at     TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    json            TEXT NOT NULL,
    UNIQUE (project_id, content_hash)
);
CREATE INDEX IF NOT EXISTS events_project_occurred_idx
    ON events(project_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS events_source_idx
    ON events(project_id, source_type, occurred_at DESC);
