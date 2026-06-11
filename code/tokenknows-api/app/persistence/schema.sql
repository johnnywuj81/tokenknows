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

-- v0.3 · IM 集成 (T16 起步: 仅 schema, 不接 provider)
-- Lark/飞书 + 钉钉 + 企微 + 邮件 (不接个人微信 - 协议封禁风险)
CREATE TABLE IF NOT EXISTS im_connections (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    platform            TEXT NOT NULL,                     -- feishu/dingtalk/wework/email
    status              TEXT NOT NULL DEFAULT 'pending',   -- pending/active/revoked
    tenant_name         TEXT,
    auth_token_enc      TEXT,                              -- Fernet ciphertext (hex)
    refresh_token_enc   TEXT,
    token_expires_at    TEXT,
    consent_signed_by   TEXT,                              -- admin user_id
    consent_user_id     TEXT,                              -- employee user_id
    consent_signed_at   TEXT,
    revoked_at          TEXT,
    last_synced_at      TEXT,
    updated_at          TEXT NOT NULL,
    json                TEXT NOT NULL                      -- 完整 IMConnection dump
);
CREATE INDEX IF NOT EXISTS im_connections_project_status_idx
    ON im_connections(project_id, status);

CREATE TABLE IF NOT EXISTS im_messages (
    id                  TEXT PRIMARY KEY,
    connection_id       TEXT NOT NULL,
    platform_chat_id    TEXT NOT NULL,                     -- group/DM/email-thread id
    platform_msg_id     TEXT NOT NULL,                     -- 原始 message_id (幂等)
    received_at         TEXT NOT NULL,
    retention_until     TEXT,                              -- 默认 received_at + 90d
    is_signal           INTEGER NOT NULL DEFAULT 0,        -- T20 SignalGate
    redacted            INTEGER NOT NULL DEFAULT 0,
    json                TEXT NOT NULL,                     -- 完整 IMMessage dump
    FOREIGN KEY (connection_id) REFERENCES im_connections(id) ON DELETE CASCADE,
    UNIQUE (connection_id, platform_msg_id)
);
CREATE INDEX IF NOT EXISTS im_messages_chat_time_idx
    ON im_messages(connection_id, platform_chat_id, received_at DESC);
CREATE INDEX IF NOT EXISTS im_messages_signal_idx
    ON im_messages(connection_id, is_signal, received_at DESC);
-- retention 扫描: WHERE retention_until <= now AND redacted = 0
CREATE INDEX IF NOT EXISTS im_messages_retention_idx
    ON im_messages(retention_until, redacted);

-- ValueSegment · 脱敏后可出域的价值片段 (跨 events / IM 共享抽象)
CREATE TABLE IF NOT EXISTS value_segments (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    source_type     TEXT NOT NULL,                         -- event / im_chat / im_thread
    trust_score     REAL NOT NULL DEFAULT 0.5,
    extracted_at    TEXT NOT NULL,
    json            TEXT NOT NULL                          -- 完整 ValueSegment dump
);
CREATE INDEX IF NOT EXISTS value_segments_project_trust_idx
    ON value_segments(project_id, trust_score DESC, extracted_at DESC);
CREATE INDEX IF NOT EXISTS value_segments_source_idx
    ON value_segments(source_type, project_id);

-- ───────────────────────────────────────────────────────────────
-- v0.4 · Auto-Trigger (T26)
-- 来源: Proposal_Automatic_Generation_Trigger_v0.4.md §8
-- 偏差说明见 app/schemas/auto_trigger.py 顶部注释
-- ───────────────────────────────────────────────────────────────

-- 触发规则定义 (实例级 project_id=NULL + 项目级 project_id=具体值 并存)
CREATE TABLE IF NOT EXISTS trigger_rules (
    id              TEXT PRIMARY KEY,
    project_id      TEXT,                                  -- NULL = 实例级默认规则
    name            TEXT NOT NULL,
    mode            TEXT NOT NULL,                         -- cron/event/threshold/mention
    asset_type      TEXT NOT NULL,                         -- weekly_report/adr/incident/book/agent_skill
    enabled         INTEGER NOT NULL DEFAULT 1,
    priority        INTEGER NOT NULL DEFAULT 50,
    updated_at      TEXT NOT NULL,
    json            TEXT NOT NULL                          -- 完整 TriggerRule dump
);
-- 主查询路径: enabled rules of given mode
CREATE INDEX IF NOT EXISTS trigger_rules_enabled_mode_idx
    ON trigger_rules(enabled, mode) WHERE enabled = 1;
CREATE INDEX IF NOT EXISTS trigger_rules_project_idx
    ON trigger_rules(project_id, enabled);
-- 实例级规则 (project_id=NULL) 单独 unique (规避 SQLite NULL!=NULL 在 UNIQUE 上的行为)
CREATE UNIQUE INDEX IF NOT EXISTS trigger_rules_instance_name_unique
    ON trigger_rules(name) WHERE project_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS trigger_rules_project_name_unique
    ON trigger_rules(project_id, name) WHERE project_id IS NOT NULL;

-- 执行历史
CREATE TABLE IF NOT EXISTS trigger_executions (
    id              TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL,
    project_id      TEXT NOT NULL,                         -- 即使规则是实例级, 执行总落在具体项目
    status          TEXT NOT NULL,                         -- scheduled/fired/canceled/skipped/failed/expired
    fire_at         TEXT NOT NULL,                         -- 计划触发 (含 5min 撤回窗口)
    fired_at        TEXT,                                  -- 实际触发完成
    asset_id        TEXT,                                  -- status=fired 时关联
    created_at      TEXT NOT NULL,
    json            TEXT NOT NULL,                         -- 完整 TriggerExecution dump
    FOREIGN KEY (rule_id) REFERENCES trigger_rules(id) ON DELETE CASCADE
);
-- T31 withdraw_resolver 主扫描路径: WHERE status='scheduled' AND fire_at <= now
CREATE INDEX IF NOT EXISTS trigger_executions_scheduled_idx
    ON trigger_executions(status, fire_at) WHERE status = 'scheduled';
-- 项目级历史时间轴 (Proposal §7.5 / 体验要素 #31)
CREATE INDEX IF NOT EXISTS trigger_executions_project_created_idx
    ON trigger_executions(project_id, created_at DESC);
-- 单规则历史
CREATE INDEX IF NOT EXISTS trigger_executions_rule_created_idx
    ON trigger_executions(rule_id, created_at DESC);

-- 月配额 (v0.4.0 仅建表; v0.4.4 真正激活)
CREATE TABLE IF NOT EXISTS generation_quotas (
    id                      TEXT PRIMARY KEY,
    project_id              TEXT NOT NULL,
    year_month              TEXT NOT NULL,                 -- 'YYYY-MM'
    monthly_token_limit     INTEGER NOT NULL DEFAULT 5000000,
    daily_auto_gen_limit    INTEGER NOT NULL DEFAULT 20,
    tokens_used             INTEGER NOT NULL DEFAULT 0,
    auto_gen_count          INTEGER NOT NULL DEFAULT 0,
    is_throttled            INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL,
    json                    TEXT NOT NULL,                 -- 完整 GenerationQuota dump
    UNIQUE (project_id, year_month)
);
CREATE INDEX IF NOT EXISTS generation_quotas_project_idx
    ON generation_quotas(project_id, year_month DESC);

-- v1.1.0 · 账户系统 (T74)
-- 邮箱 + bcrypt 密码 + JWT issue (替换 v0.9 X-User-Id MVP)
CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    email               TEXT NOT NULL UNIQUE,
    display_name        TEXT NOT NULL,
    password_hash       TEXT NOT NULL,                 -- bcrypt
    is_instance_admin   INTEGER NOT NULL DEFAULT 0,
    last_login_at       TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    json                TEXT NOT NULL                  -- 完整 User dump
);
CREATE INDEX IF NOT EXISTS users_email_idx ON users(email);

-- v0.9.0 · 项目成员 + 角色 (T65)
-- 一个 user 在一个 project 内仅 1 role; 同 user 跨 project 各自一行.
CREATE TABLE IF NOT EXISTS project_members (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,         -- owner / reviewer / contributor
    added_by    TEXT NOT NULL,
    added_at    TEXT NOT NULL,
    json        TEXT NOT NULL,         -- 完整 ProjectMember dump
    UNIQUE (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS project_members_project_role_idx
    ON project_members(project_id, role);
CREATE INDEX IF NOT EXISTS project_members_user_idx
    ON project_members(user_id);

-- v0.5.1 · 站内通知 (T49 ConsentNotifier 主表)
-- 关键索引: (user_id, read, created_at DESC) 服务铃铛角标查询.
CREATE TABLE IF NOT EXISTS notifications (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,                 -- 接收者 platform user_id
    type                TEXT NOT NULL,                 -- consent_request / consent_signed / consent_rejected / consent_expired
    related_skill_id    TEXT,                          -- 反查方便
    read                INTEGER NOT NULL DEFAULT 0,    -- 0/1
    created_at          TEXT NOT NULL,
    json                TEXT NOT NULL                  -- 完整 WebNotification dump
);
CREATE INDEX IF NOT EXISTS notifications_user_unread_idx
    ON notifications(user_id, read, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_skill_idx
    ON notifications(related_skill_id) WHERE related_skill_id IS NOT NULL;

-- v2.1 · Personal Access Tokens (MCP / API 长期凭据)
-- 明文永不落库: token_hash = sha256(plaintext); token_prefix 仅 UI 辨识用.
CREATE TABLE IF NOT EXISTS api_tokens (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    token_prefix    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    revoked_at      TEXT,
    json            TEXT NOT NULL                  -- 完整 ApiToken dump
);
CREATE INDEX IF NOT EXISTS api_tokens_user_idx
    ON api_tokens(user_id, created_at DESC);
