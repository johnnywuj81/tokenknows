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
    parent_id   TEXT,                  -- v0.2: book 嵌套大纲 (NULL = 顶层章)
    depth       INTEGER DEFAULT 0,     -- v0.2: 0=卷, 1=章, 2=节 (4 类现有都是 0)
    json        TEXT NOT NULL,         -- 完整 Chapter dump (含 applied_skills 等 v0.2 字段)
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chapters_asset_idx ON chapters(asset_id, order_index);
-- chapters_parent_idx 在 store.py:_apply_migrations() 里创建 (避免老 DB 缺 parent_id 列时报错)

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

-- v0.2 · Skills · 蒸馏出的 Agent 专家技能 (项目级私有 MVP)
-- 字段说明:
--   trust_score: 注入下游生成时 top-k 排序用 (高分优先)
--   status:      draft (待审批) / active (可被注入) / deprecated (停用)
--   json:        完整 Skill dump (含 skill_md / embedding / metrics / distilled_from)
CREATE TABLE IF NOT EXISTS skills (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'draft',
    trust_score  REAL NOT NULL DEFAULT 0.5,
    updated_at   TEXT NOT NULL,
    json         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS skills_project_idx
    ON skills(project_id, status);
CREATE INDEX IF NOT EXISTS skills_trust_idx
    ON skills(project_id, status, trust_score DESC);
-- 同名 skill 不同 version 共存; (project_id, name, version) 不强制唯一
-- 避免 evolve_skill_v2 race (rare 但可能); 业务层去重
