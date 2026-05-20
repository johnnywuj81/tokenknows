# TDD · TokenKnows MVP

> 技术设计文档 · 把 PRD §6 / §7 展开到代码与部署层

---

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | TokenKnows MVP 技术设计文档 |
| 版本 | v0.1 |
| 状态 | 起草中 |
| 关联文档 | [BRD](./BRD_AI研发知识资产引擎.md) · [PRD](./PRD_TokenKnows_MVP.md) |
| 目标读者 | 后端 / 前端 / DevOps / QA |
| 文档目的 | 给研发提供可直接对照实施的架构、技术栈、Schema、API、部署细节 |

---

## 2. 架构总览

### 2.1 分层

```
┌─────────────────────────────────────────────────────┐
│  Frontend · React + TipTap + shadcn/ui              │   浏览器
├─────────────────────────────────────────────────────┤
│  API Gateway · FastAPI                              │   HTTPS / SSE / WS
├─────────────────────────────────────────────────────┤
│  Application Services                               │
│    Project / Ingestion / Value Extraction /         │
│    Generation / Redaction / Publish                 │
├─────────────────────────────────────────────────────┤
│  LLM Gateway · 统一适配                              │
│  ┌──────────┬──────────┬──────────┬──────────────┐ │
│  │Anthropic │ OpenAI   │ Ollama   │  vLLM        │ │
│  └──────────┴──────────┴──────────┴──────────────┘ │
├─────────────────────────────────────────────────────┤
│  Storage Layer                                      │
│    Postgres 15 (含 pgvector) · Redis 7 · S3/MinIO   │
└─────────────────────────────────────────────────────┘
                          ▲
                          │
              ┌───────────┴────────────┐
              │  客户端采集（plugin）     │
              │  Claude Code / Cursor /  │
              │  VS Code + Copilot Chat  │
              └───────────┬──────────────┘
                          │
              ┌───────────┴────────────┐
              │  GitHub API（PAT+Webhook）│
              └────────────────────────────┘
```

### 2.2 部署形态

参见 PRD §6.5：

- **Compose 简易版**：所有服务 + Postgres / Redis / MinIO 单机部署，`docker compose up -d`
- **K8s 企业版**：业务服务无状态 + 外置数据存储；Helm Chart 部署

**架构铁律**：业务代码完全一致；差异**只**通过环境变量 + Helm values 表达。禁止 `if PRIVATE_DEPLOYMENT` 之类的代码分支。

### 2.3 关键设计原则

1. **业务代码 ⊥ 部署形态**：所有差异通过环境变量与配置抽象表达
2. **LLM 调用全走 Gateway**：业务代码不允许 `import anthropic` / `import openai`
3. **服务无状态**：除存储层外可水平扩展
4. **采集层独立**：插件 / 扩展为客户端，不影响后端可用性
5. **私有化首要**：数据默认零出域；任何 outbound 都过门禁

---

## 3. 技术栈

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 后端语言 | Python 3.11 | LLM 生态最全；FastAPI 异步性能够 MVP 用 |
| Web 框架 | FastAPI | async 原生、Pydantic 类型化、自动 OpenAPI |
| 任务编排 | Celery + Redis | 文档生成等长任务异步执行 |
| ORM | SQLAlchemy 2.x (async) + Alembic | 标准 |
| 数据库 | PostgreSQL 15 + pgvector + tsvector | 关系 + 向量 + 全文 三合一 |
| 缓存 | Redis 7 | session / 限流 / 队列 / 事件流 fan-out |
| 对象存储 | S3 兼容（Compose 内置 MinIO） | 大文本、导出产物、版本快照 |
| 实时通信 | SSE（主） + WebSocket（少量） | SSE 实现简单，覆盖 90% 实时场景 |
| 前端 | React 18 + TypeScript + Vite | 主流生态 |
| 状态 | Zustand + TanStack Query | 轻 + Server State 自动同步 |
| UI 组件库 | shadcn/ui + Tailwind | 可控可改、不锁主题 |
| 编辑器 | TipTap | 富文本 + 自定义节点（证据徽章 / 脱敏占位） |
| 鉴权 | JWT RS256 + Argon2id | 标准 |
| 容器 | Docker + Buildx | 多架构镜像 |
| 编排 | K8s + Helm 3 | 企业标准 |
| 可观测性 | OpenTelemetry + Prometheus + Loki | 三件套，Helm Chart 内置 |
| CI/CD | GitHub Actions | 与 GitHub 数据源天然契合 |
| 测试 | pytest / playwright / k6 | 单元 / E2E / 性能 |

**关键不选**：

- 不选 Node 后端：LLM SDK 生态 Python 更完整
- 不选 GraphQL：MVP 规模 REST + SSE 已足够
- 不选 NATS：Redis Stream 单一组件即可覆盖
- 不选 Postgres + Elasticsearch 双库：pgvector + tsvector 在 MVP 规模下够用

---

## 4. 服务架构

### 4.1 进程划分（最小集）

| 进程 | 镜像 | 职责 | 副本（K8s 推荐） |
| --- | --- | --- | --- |
| `web` | tokenknows/web | 静态资源（CDN 可选） | 1-2 |
| `api` | tokenknows/api | REST / SSE / WS | 2+ |
| `worker-ingest` | tokenknows/worker | 采集事件持久化 + GitHub 轮询 | 1-2 |
| `worker-extract` | tokenknows/worker | 价值识别 | 2+ |
| `worker-generate` | tokenknows/worker | 文档生成 + 脱敏识别 | 2+ |
| `worker-publish` | tokenknows/worker | 外发到目的地 | 1 |

worker 用同一份镜像，通过 `WORKER_QUEUES` 环境变量决定订阅哪些队列。

### 4.2 模块边界（同进程内）

`api` 进程内的逻辑层：

```
api/
├── auth/               # 鉴权
├── projects/           # 项目 CRUD + 角色
├── datasources/        # 数据源 CRUD + GitHub PAT + webhook 接收
├── events/             # 事件读写 + 实时流 fan-out
├── assets/             # Asset / Chapter / Evidence 编辑
├── generation/         # 触发生成 + 状态查询
├── redaction/          # 扫描 + 确认
├── publish/            # 发布 + 撤回
├── audit/              # 审计 / 出域日志查询
├── llm_gateway/        # LLM 抽象层
└── core/               # 配置、依赖注入、中间件
```

---

## 5. 数据库 Schema

完整 DDL 见 `schema.sql`；下面仅列关键表。

### 5.1 用户与项目

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,           -- Argon2id
  display_name TEXT NOT NULL,
  is_instance_admin BOOLEAN DEFAULT FALSE,
  email_verified_at TIMESTAMPTZ,
  failed_login_count INT DEFAULT 0,
  locked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  owner_id UUID NOT NULL REFERENCES users(id),
  llm_egress_enabled BOOLEAN DEFAULT FALSE,   -- 项目级出域开关
  task_egress_config JSONB DEFAULT '{}',      -- 任务级开关
  custom_redaction_terms JSONB DEFAULT '[]',
  brand_theme JSONB DEFAULT '{}',
  retention_policy JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE project_members (
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  role TEXT CHECK (role IN ('owner','editor','reviewer','viewer')) NOT NULL,
  added_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (project_id, user_id)
);

CREATE TABLE instance_settings (
  key TEXT PRIMARY KEY,
  value JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  updated_by UUID REFERENCES users(id)
);
-- 例：instance_egress_enabled / default_llm_provider / license_status
```

### 5.2 Event 与 ValueSegment

```sql
CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  external_id TEXT NOT NULL,
  version INT DEFAULT 1,
  event_type TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  author JSONB,
  title TEXT,
  content TEXT,                          -- inline 直存
  content_blob_ref TEXT,                 -- > 32KB 时写 MinIO，存 key
  content_size_bytes INT,
  payload JSONB,
  redaction_state TEXT DEFAULT 'raw',
  trust_score FLOAT,
  tags TEXT[],
  content_hash TEXT,                     -- SHA256(content)
  embeddings vector(1536),               -- pgvector
  CONSTRAINT events_source_unique
    UNIQUE (source_type, source_ref, external_id, version)
);

CREATE INDEX idx_events_project_time
  ON events (project_id, occurred_at DESC);
CREATE INDEX idx_events_tags
  ON events USING GIN (tags);
CREATE INDEX idx_events_hash
  ON events (content_hash);
CREATE INDEX idx_events_embed
  ON events USING ivfflat (embeddings vector_cosine_ops) WITH (lists = 100);
-- tsvector 索引按需补充

CREATE TABLE value_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  span_start INT NOT NULL,
  span_end INT NOT NULL,
  category TEXT,
  trust_score FLOAT,
  category_confidence FLOAT,
  manual_trust_override INT,             -- 1 (trust)/-1 (distrust)/null
  extraction_state TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_segments_event ON value_segments (event_id);
CREATE INDEX idx_segments_trust ON value_segments (trust_score DESC);
```

### 5.3 Asset / Chapter / Evidence / PublishRecord

```sql
CREATE TABLE assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT DEFAULT 'draft',
  current_version INT DEFAULT 1,
  template_id TEXT,
  created_by UUID REFERENCES users(id),
  approval_state TEXT DEFAULT 'pending',
  redaction_state TEXT DEFAULT 'any_unresolved',
  metrics JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  asset_version INT NOT NULL,
  order_index INT NOT NULL,
  title TEXT,
  content TEXT,
  content_blob_ref TEXT,                  -- > 64KB 时存对象存储
  layout JSONB,
  generated_by JSONB,                     -- {model, provider, latency_ms, tokens}
  regeneration_history JSONB DEFAULT '[]',
  approval_state TEXT DEFAULT 'pending',
  redacted_spans JSONB DEFAULT '[]',
  UNIQUE (asset_id, asset_version, order_index)
);

CREATE TABLE evidences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  event_id UUID NOT NULL REFERENCES events(id),
  event_version INT NOT NULL,
  span_start INT NOT NULL,
  span_end INT NOT NULL,
  citation_text TEXT,
  manually_added BOOLEAN DEFAULT FALSE,
  stale BOOLEAN DEFAULT FALSE
);

CREATE TABLE publish_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(id),
  asset_version INT NOT NULL,
  destination TEXT NOT NULL,
  destination_ref TEXT,
  publish_mode TEXT,
  status TEXT,
  url TEXT,
  published_at TIMESTAMPTZ DEFAULT NOW(),
  published_by UUID REFERENCES users(id)
);
```

### 5.4 审计与出域日志

```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID,
  project_id UUID,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id UUID,
  diff JSONB,
  ip TEXT,
  user_agent TEXT
);
CREATE INDEX idx_audit_project_time ON audit_log (project_id, ts DESC);
CREATE INDEX idx_audit_user_time ON audit_log (user_id, ts DESC);

CREATE TABLE egress_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ DEFAULT NOW(),
  project_id UUID,
  user_id UUID,
  task TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  request_size_bytes INT,
  response_size_bytes INT,
  prompt_tokens INT,
  completion_tokens INT,
  latency_ms INT,
  cost_estimate NUMERIC,
  hash_of_request TEXT,
  fallback_used BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_egress_project_time ON egress_log (project_id, ts DESC);
```

### 5.5 分区与冷热分层

- **events 表**按 `occurred_at` 按月分区（pg_partman）
- 热数据（最近 90 天）：主存储 + 索引
- 温数据（91 天 - 1 年）：分区表 + 索引（视情况裁减）
- 冷数据：每月定时归档为 Parquet 写入 MinIO；查询通过 DuckDB 外部表（Phase 2 实现）

---

## 6. API 设计

### 6.1 主要 REST 端点

```
# Auth
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/me
POST   /api/v1/me/verify-email

# Projects
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}
PATCH  /api/v1/projects/{id}
DELETE /api/v1/projects/{id}                # 软删

# Members
GET    /api/v1/projects/{id}/members
POST   /api/v1/projects/{id}/members
PATCH  /api/v1/projects/{id}/members/{user_id}
DELETE /api/v1/projects/{id}/members/{user_id}

# Datasources
GET    /api/v1/projects/{id}/datasources
POST   /api/v1/projects/{id}/datasources/github
POST   /api/v1/projects/{id}/datasources/local-file
DELETE /api/v1/projects/{id}/datasources/{ds_id}
GET    /api/v1/projects/{id}/datasources/{ds_id}/health

# Plugin 上报
POST   /api/v1/ingestion/events            # 插件批量上报（带连接 token）
POST   /api/v1/ingestion/webhook/github    # GitHub webhook

# Events
GET    /api/v1/projects/{id}/events?from=&to=&source_type=&author=
GET    /api/v1/projects/{id}/events/{event_id}

# Generation
POST   /api/v1/projects/{id}/assets/generate
       body: { type, time_window, source_filter, model_override }
GET    /api/v1/assets/{asset_id}
PATCH  /api/v1/assets/{asset_id}/chapters/{chapter_id}
POST   /api/v1/assets/{asset_id}/chapters/{chapter_id}/regenerate
       body: { instruction, model }

# Evidence
GET    /api/v1/assets/{asset_id}/chapters/{chapter_id}/evidence?span_start=&span_end=
POST   /api/v1/assets/{asset_id}/chapters/{chapter_id}/evidence
DELETE /api/v1/evidence/{evidence_id}

# Review / Approval
POST   /api/v1/assets/{asset_id}/submit
POST   /api/v1/assets/{asset_id}/chapters/{chapter_id}/approve
POST   /api/v1/assets/{asset_id}/chapters/{chapter_id}/reject
POST   /api/v1/assets/{asset_id}/comments

# Redaction
POST   /api/v1/assets/{asset_id}/redaction/scan
POST   /api/v1/assets/{asset_id}/redaction/confirm
POST   /api/v1/assets/{asset_id}/redaction/exempt

# Export & Publish
POST   /api/v1/assets/{asset_id}/export
       body: { format: md|docx|pdf }
POST   /api/v1/assets/{asset_id}/publish
       body: { destinations[], publish_mode }
POST   /api/v1/publish-records/{id}/revoke

# Audit
GET    /api/v1/audit-log?project_id=&user_id=&action=
GET    /api/v1/egress-log?project_id=
```

### 6.2 SSE / WebSocket

- `GET /api/v1/ws/projects/{id}/events` (SSE)：订阅项目实时事件流
- `GET /api/v1/ws/assets/{asset_id}/generation` (SSE)：订阅生成进度（5 阶段事件）
- WebSocket 仅用于编辑器协作（章节级锁定通知）

后端通过 Redis Pub/Sub 实现 fan-out。

### 6.3 OpenAPI

FastAPI 自动生成 `/openapi.json`；前端通过 `openapi-typescript-codegen` 生成类型化 client。

---

## 7. LLM Gateway 实现

### 7.1 接口定义

```python
from typing import Literal, Optional, Protocol
from pydantic import BaseModel
from uuid import UUID

class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class LLMOptions(BaseModel):
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    json_mode: bool = False
    timeout_seconds: float = 120

class LLMResponse(BaseModel):
    text: str
    usage: dict             # {prompt_tokens, completion_tokens, total_tokens}
    model_used: str
    provider: str
    latency_ms: int
    fallback_used: bool = False

LLMTask = Literal[
    "value_extraction",
    "weekly_report",
    "tech_design",
    "adr",
    "incident",
    "redaction_llm",
]

class LLMGateway(Protocol):
    async def generate(
        self,
        task: LLMTask,
        messages: list[LLMMessage],
        options: LLMOptions,
        project_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> LLMResponse: ...
    
    async def stream(
        self, task, messages, options, project_id, user_id=None
    ) -> AsyncIterator[str]: ...
```

### 7.2 适配器骨架

```python
class BaseAdapter(ABC):
    provider: str
    is_cloud: bool   # True for Anthropic/OpenAI; False for Ollama/vLLM
    
    @abstractmethod
    async def generate(self, messages, options) -> LLMResponse: ...
    
    @abstractmethod
    async def stream(self, messages, options) -> AsyncIterator[str]: ...

class AnthropicAdapter(BaseAdapter):
    provider = "anthropic"
    is_cloud = True
    # 调用 anthropic SDK

class OpenAIAdapter(BaseAdapter):
    provider = "openai"
    is_cloud = True

class OllamaAdapter(BaseAdapter):
    provider = "ollama"
    is_cloud = False
    # 走 HTTP / Ollama 默认 11434

class VLLMAdapter(BaseAdapter):
    provider = "vllm"
    is_cloud = False
    # OpenAI-compatible API
```

### 7.3 路由与门禁

```python
class LLMRouter:
    def select_adapter(self, task: LLMTask, project_id: UUID) -> BaseAdapter:
        # 1. 读取 task → provider 映射（项目级覆盖 / 实例级默认）
        # 2. 加载该 provider 的 adapter
        # 3. 检查三层出域开关
        adapter = self._lookup_primary(task, project_id)
        if adapter.is_cloud and not self._egress_allowed(task, project_id):
            adapter = self._lookup_fallback_local(task, project_id)
            if adapter is None:
                raise EgressDeniedError(task=task, project_id=project_id)
        return adapter
    
    def _egress_allowed(self, task, project_id) -> bool:
        instance = self.instance_settings.get("instance_egress_enabled", False)
        project = self.db.get_project(project_id).llm_egress_enabled
        task_level = self.db.get_project(project_id).task_egress_config.get(task, False)
        return instance and project and task_level
```

### 7.4 调用全流程

```python
async def generate(self, task, messages, options, project_id, user_id=None):
    adapter = self.router.select_adapter(task, project_id)
    start = time.monotonic()
    try:
        result = await adapter.generate(messages, options)
    except Exception as e:
        # 尝试 fallback
        fallback = self.router.next_fallback(task, project_id, exclude=adapter.provider)
        if fallback is None:
            raise
        result = await fallback.generate(messages, options)
        result.fallback_used = True
    
    latency = int((time.monotonic() - start) * 1000)
    
    # 出域日志（仅云端 adapter）
    if adapter.is_cloud:
        await self.audit.record_egress(
            project_id, user_id, task, adapter.provider, 
            messages, result, latency
        )
    
    return result
```

---

## 8. 采集层（Plugin / Extension Protocol）

### 8.1 通用上报协议

所有插件 / 扩展按下面格式上报：

```http
POST /api/v1/ingestion/events
Authorization: Bearer <connection_token>
Content-Type: application/json

{
  "batch_id": "uuid",
  "events": [
    {
      "source_type": "claude_code",
      "source_ref": "install-abc-123",
      "external_id": "conv-xyz:turn-7",
      "version": 1,
      "event_type": "ai_conversation_turn",
      "occurred_at": "2026-05-19T10:00:00Z",
      "author": {"name": "alice", "email": "alice@example.com"},
      "content": "<markdown>",
      "payload": {
        "model": "claude-sonnet-4-6",
        "tool_calls": [{"name": "edit_file", "args": {...}}],
        "files_changed": ["src/app.py"]
      }
    }
  ]
}
```

返回 `{ accepted: N, rejected: [{external_id, reason}] }`。

### 8.2 连接 token

- 用户在 Web 控制台创建项目时生成 token（项目级，长期有效）
- token = `{project_id}.{random}.{signature}`，HMAC-SHA256 签名
- 失效时可在 Web 端撤销重发
- 插件本地以受限权限写入 `~/.tokenknows/config.json`

### 8.3 本地缓冲

每个插件本地维护 ring buffer：

- 默认 100MB / 7 天
- LevelDB 实现（跨平台、低依赖）
- 上传成功的 batch 标记已确认
- 启动时检查未确认 batch，重传

### 8.4 平台差异要点

| 插件 | 关键 hook | 兜底 |
| --- | --- | --- |
| Claude Code | session lifecycle + tool call event | 解析 `~/.claude/sessions/*.jsonl` |
| Cursor | chat history file watcher | 用户手动导出 JSON 上传 |
| VS Code | Copilot Chat API + workspace.onDidChangeTextDocument | 剪贴板复制 + 手动绑定（PRD §10 风险记录） |
| GitHub | webhook + polling | 60s 间隔轮询；rate-limit 退避 |

---

## 9. 安全实现

### 9.1 鉴权

- **密码哈希**：Argon2id（`memory_cost=64MB, time_cost=3, parallelism=1`）
- **JWT**：RS256 签名，access token 15 分钟，refresh token 7 天
- **公私钥**：实例首启动时生成（4096-bit RSA），存 vault
- **登录失败**：5 次锁定 15 分钟；记录到审计

### 9.2 授权（RBAC）

`require_role` 装饰器统一处理：

```python
@router.post("/projects/{id}/datasources/github")
@require_role(project_id="id", role=["owner"])
async def add_github_datasource(...): ...

@router.post("/assets/{asset_id}/chapters/{chapter_id}/approve")
@require_role(asset_id="asset_id", role=["reviewer", "owner"])
async def approve_chapter(...): ...
```

### 9.3 加密

| 项 | 实现 |
| --- | --- |
| 传输加密 | HTTPS / TLS 1.2+；HSTS；禁用弱密码套件 |
| 静态加密 | Postgres TDE（视环境）+ 应用层 vault 加密敏感字段 |
| Vault 简易实现 | sqlite + libsodium SecretBox；master key 来自启动 env |
| Vault 企业版 | 可挂 HashiCorp Vault / AWS KMS |
| 敏感字段 | GitHub PAT / LLM API Key / 连接 token / 用户 OAuth refresh |

### 9.4 审计

每个写 API 用 `@audited(action="...")` 装饰器：

```python
@router.patch("/projects/{id}")
@audited(action="project.update", resource_type="project", resource_id="id")
async def update_project(...): ...
```

中间件自动捕获 before/after JSON diff，写入 audit_log。

---

## 10. 部署架构

### 10.1 Compose 简易版

```yaml
# docker-compose.yml（节选）
version: "3.9"

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7
    volumes:
      - redis_data:/data
  
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
  
  api:
    image: tokenknows/api:${VERSION}
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${DB_PASSWORD}@postgres:5432/tokenknows
      REDIS_URL: redis://redis:6379/0
      OBJECT_STORAGE_ENDPOINT: http://minio:9000
      LICENSE_PATH: /etc/tokenknows/license.bin
    depends_on: [postgres, redis, minio]
    ports: ["8000:8000"]
  
  worker:
    image: tokenknows/worker:${VERSION}
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${DB_PASSWORD}@postgres:5432/tokenknows
      REDIS_URL: redis://redis:6379/0
      WORKER_QUEUES: ingest,extract,generate,publish
    depends_on: [postgres, redis]
  
  web:
    image: tokenknows/web:${VERSION}
    ports: ["80:80"]
    depends_on: [api]

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

提供 `setup.sh` 引导用户：生成密码、license 验签、初次 migration、健康检查。目标 30 分钟内上线。

### 10.2 K8s Helm Chart 结构

```
charts/tokenknows/
├── Chart.yaml
├── values.yaml                # 默认值（开发用）
├── values-prod-example.yaml   # 生产参考
├── templates/
│   ├── deployment-api.yaml
│   ├── deployment-worker-{ingest,extract,generate,publish}.yaml
│   ├── deployment-web.yaml
│   ├── service-{api,web}.yaml
│   ├── ingress.yaml
│   ├── secret-{db,llm,license}.yaml
│   ├── configmap.yaml
│   ├── pdb.yaml               # PodDisruptionBudget
│   ├── hpa.yaml               # HorizontalPodAutoscaler
│   └── _helpers.tpl
├── charts/                    # 可选子 chart：bundled postgres / redis / minio
└── README.md
```

外置依赖（生产推荐）：

- Postgres：客户提供（RDS / 自建）
- Redis：客户提供（ElastiCache / 自建）
- S3：客户提供（S3 / OSS / COS / MinIO）

通过 values.yaml：

```yaml
postgres:
  bundled: false
  url: "postgresql+asyncpg://..."   # 客户填
redis:
  bundled: false
  url: "redis://..."
objectStorage:
  bundled: false
  endpoint: "https://s3.amazonaws.com"
  bucket: "tokenknows-prod"
  accessKey: "AKIA..."
  secretKey: ""
```

### 10.3 升级机制

- 镜像版本化 SemVer（`vMAJOR.MINOR.PATCH`）
- 启动时 `alembic upgrade head` 应用迁移
- 失败 → exit code ≠ 0 → K8s 自动回滚到上一稳定 Pod
- Major 升级需运维操作：先 `alembic upgrade --sql > migration.sql` dry-run

### 10.4 License 验签

```python
import json, base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def verify_license(license_path: str, public_key_path: str) -> dict:
    with open(license_path, "rb") as f:
        envelope = json.loads(f.read())
    payload_b64 = envelope["payload"]
    signature_b64 = envelope["signature"]
    
    with open(public_key_path, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    
    payload = base64.b64decode(payload_b64)
    signature = base64.b64decode(signature_b64)
    pub.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
    
    data = json.loads(payload)
    # 校验 expires_at / instance_limit
    return data
```

启动时调用；过期 / 缺失 → 进入只读模式（已采数据可看，不可生成）。

---

## 11. 性能与可观测性

### 11.1 性能要点

| 项 | 实现 |
| --- | --- |
| 文档生成异步 | Celery 任务 + Redis 队列；前端 SSE 订阅进度 |
| 大文档流式渲染 | 后端 SSE 流式输出 token；前端 React 增量 render |
| 数据库索引 | 按 §5 schema 已定义 |
| LLM 调用并发 | adapter 内 `asyncio.Semaphore`（默认 10 并发） |
| 缓存 | 项目级元数据 / LLM 路由配置 → Redis（TTL 60s） |

### 11.2 可观测性

- **指标**：FastAPI `prometheus_fastapi_instrumentator` + 自定义业务指标
- **日志**：`structlog` + JSON 输出；Trace ID 全链路注入
- **链路**：OpenTelemetry SDK；Jaeger 协议
- **告警**：Helm Chart 内置 Prometheus alert rules（采集断连、生成超时、LLM 异常、磁盘 / DB 健康）

Grafana 面板模板随发布：

- ops dashboard：CPU / Memory / DB / 队列深度 / HTTP 错误率
- business dashboard：采集成功率、生成时延、自评分布、人工修改率

---

## 12. 测试策略

| 类型 | 工具 | 触发 | 目标 |
| --- | --- | --- | --- |
| 单元测试 | pytest | 每 PR | 行覆盖 ≥ 70% |
| 集成测试 | pytest + testcontainers | 每 PR | 关键路径 happy + edge |
| 前端单元 | vitest + react-testing-library | 每 PR | 组件覆盖 ≥ 60% |
| E2E | playwright | 每日 nightly | 8-10 个核心 user flow |
| 性能 | k6 | 每 Sprint 末 | §6.1 SLA |
| 安全 | trivy / bandit / npm audit | 每 PR | 阻塞高危 CVE |
| LLM 输出回归 | 自研 + golden set | 模型升级 / Prompt 修改 | 关键指标稳定 |

LLM 输出回归思路：维护一个 100 条左右的 (input → expected) golden set，每次 Prompt / 模型变动跑一次，对比 coverage / citation density / slop_score 几个指标的 drift。

---

## 13. 开发节奏与代码规范

- **代码仓库**：单 monorepo
  ```
  tokenknows/
  ├── apps/
  │   ├── api/        # FastAPI 后端
  │   ├── worker/     # Celery worker
  │   ├── web/        # React 前端
  │   ├── plugin-claude-code/
  │   ├── plugin-cursor/
  │   └── plugin-vscode/
  ├── packages/
  │   ├── shared-types/
  │   └── shared-utils/
  ├── charts/         # Helm Chart
  ├── compose/        # Docker Compose
  ├── scripts/
  └── docs/
  ```
- **Branch**：trunk-based，每 PR 跑全套 CI
- **代码规范**：
  - Python：ruff + black + mypy
  - TS：eslint + prettier + typescript strict
- **Commit**：Conventional Commits
- **PR 模板**：变更摘要 / 测试覆盖 / 风险与回滚方案 / 涉及的 PRD 章节

---

## 14. 风险与开放问题（待研发评估）

1. **pgvector 性能**：单实例 events 表 > 10M 行时索引重建与查询性能未实测；需要在 S3 跑性能 spike
2. **Copilot Chat API 兼容性**：S6 启动前必须用真实 API 跑可行性 spike（参见 PRD §10 风险表）
3. **Celery 在私有化场景的运维复杂度**：考虑改用 ARQ / Dramatiq（更轻量）
4. **MinIO 在生产环境的可靠性**：客户更可能用 S3 兼容产品；Compose 内置仅作 dev / PoC
5. **简易 vault 是否够安全**：若试点客户合规要求高，应允许接外部 vault（HashiCorp Vault / AWS KMS）

---

## 附录

### 附录 A · 关键环境变量清单

```
# 部署
TOKENKNOWS_VERSION
DEPLOYMENT_MODE          # compose | k8s
INSTANCE_ID
LICENSE_PATH

# 存储
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY
OBJECT_STORAGE_SECRET_KEY

# 鉴权
JWT_PRIVATE_KEY_PATH
JWT_PUBLIC_KEY_PATH
VAULT_MASTER_KEY

# LLM
DEFAULT_LLM_PROVIDER     # anthropic | openai | ollama | vllm
ANTHROPIC_API_KEY        # 仅在出域开启且选 Anthropic 时
OPENAI_API_KEY
OLLAMA_BASE_URL
VLLM_BASE_URL

# 出域
INSTANCE_EGRESS_ENABLED  # 默认 false

# 可观测
OTEL_EXPORTER_OTLP_ENDPOINT
METRICS_PORT             # default 9090
```

### 附录 B · 第一个迭代 (S1) 的明确交付物清单

详见 PRD §11；TDD 维度补充：

- API 项目骨架（FastAPI + Alembic + 基础中间件）
- Web 前端骨架（Vite + React + Tailwind + shadcn/ui + Router）
- Compose 配置可启动 5 个核心服务
- 数据库初始 schema（users / projects / project_members）
- 鉴权完整链路（注册 / 登录 / JWT / 中间件）
- LLM Gateway 接口定义 + Anthropic 适配器骨架
- 基础 CI（lint / test / build）
- 一份完整开发环境的 README
