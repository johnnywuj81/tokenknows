# TokenKnows MVP · 架构与里程碑（施工层）

> 本文档是工程交付层的"施工动线"层。它**不取代** [PRD](../PRD_TokenKnows_MVP.md) / [TDD](../TDD_TokenKnows_MVP.md) / [DesignHandoff](../DesignHandoff_TokenKnows_MVP.md)，而是把它们串成一张"谁在哪个 Sprint 做什么、复用哪份既有代码、过哪些闸"的执行视图。
>
> | 项 | 内容 |
> |---|---|
> | 文档版本 | v0.1 |
> | 撰写日期 | 2026-05-20 |
> | 适用读者 | Solo 主程 + Claude Code / Cursor 代理；后续加入的全栈 / DevOps |
> | 关联文档 | [BRD](../BRD_AI研发知识资产引擎.md) · [PRD](../PRD_TokenKnows_MVP.md) · [TDD](../TDD_TokenKnows_MVP.md) · [Pitch](../Pitch_TokenKnows_Pilot.md) · [Eng README](./README.md) |
> | 复用源 | `/Users/wujun/digital_enterprise` (Agenomics / WorkDAO 生产代码) |

---

## 1. 商业产品速读（半页 alignment）

| 维度 | 关键判断 |
|---|---|
| 产品定位 | AI 研发**知识资产操作系统**（不是知识库问答、不是文档协作、不是 PR Review） |
| 核心闭环 | 采集 → 价值识别 → 文档生成 → 证据链 → 脱敏 → 审批 → 发布（**七环节全覆盖**） |
| 北极星 | 周活项目数 × 项目内已发布资产数 |
| MVP 主张 | **私有化优先 + 默认零出域 + 客户密钥客户管** |
| 商业入口 | 12 周免费深度共建 → 早鸟付费 / 私有化部署 |
| 模板范围（MVP） | 周报 / 技术方案 / ADR / 问题复盘（4 类） |
| 数据源（MVP） | Claude Code / Cursor / VS Code+Copilot / GitHub PAT / 本地文件 |
| LLM 适配 | Anthropic / OpenAI / Ollama / vLLM 四适配器 + **三层出域门禁** |
| 部署 | Docker Compose 简易版 + K8s Helm 企业版（**同一份代码、配置差异化**） |

**5 条架构铁律**（PRD §6.5 / TDD §2.3 / Pitch §5）：

1. **业务代码 ⊥ 部署形态**：Compose / K8s 差异**仅**通过环境变量 + Helm values 表达。禁 `if PRIVATE_DEPLOYMENT` 之类的分支。
2. **LLM 调用必须走 Gateway**：业务代码不允许 `import anthropic / openai / ollama`。CI 用 `ruff flake8-tidy-imports` 强制。
3. **采集层独立运行**：客户端插件 / 扩展跑在客户机器上，服务端宕机不影响采集（本地 ring buffer 100MB/7d 兜底）。
4. **事件 / 资产分层不可变**：Event 用 `(source_type, source_ref, external_id, version)` 唯一索引；Asset 发布即冻结快照。
5. **出域默认 OFF**：实例级 ∧ 项目级 ∧ 任务级三 ON 才允许 cloud adapter；任何 cloud 调用强制写 `egress_log`。

---

## 2. 整体架构总览

### 2.1 分层图

```
┌──────────────────────────────────────────────────────────────────┐
│  客户端采集层（运行在客户机器上，私有化边界外）                       │
│  ┌──────────┬──────────┬──────────┬───────────────────────────┐ │
│  │Claude    │ Cursor   │ VS Code  │ GitHub Webhook +          │ │
│  │Code      │ ext      │ ext      │ Polling (PAT)             │ │
│  │plugin    │          │ (Copilot)│                           │ │
│  └────┬─────┴────┬─────┴────┬─────┴──────────┬────────────────┘ │
└───────┼──────────┼──────────┼────────────────┼──────────────────┘
        │ Bearer token + batch JSON over HTTPS │
        ▼                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  私有化实例（客户内网，统一镜像，一行环境变量切换形态）                │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Web · React 19 + Vite 8 + Tailwind v4 + shadcn + TipTap    │ │
│  │   路由 / 编辑器 / SSE 客户端                                │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │ REST / SSE / 少量 WS                 │
│  ┌────────────────────────▼───────────────────────────────────┐ │
│  │ API Gateway · FastAPI (asgi)                               │ │
│  │   auth · projects · datasources · events · assets ·        │ │
│  │   generation · redaction · publish · audit                 │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │ Redis queue + pub/sub                │
│  ┌────────────────────────▼───────────────────────────────────┐ │
│  │ Workers · Celery（同镜像，按 WORKER_QUEUES 订阅队列）        │ │
│  │   ingest │ extract │ generate │ publish                    │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  ┌────────────────────────▼───────────────────────────────────┐ │
│  │ LLM Gateway · 统一适配 + 三层出域门禁 + 出域审计              │ │
│  │ ┌───────────┬──────────┬──────────┬─────────────────────┐  │ │
│  │ │ Anthropic │ OpenAI   │ Ollama   │ vLLM (OAI 兼容)     │  │ │
│  │ └───────────┴──────────┴──────────┴─────────────────────┘  │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  ┌────────────────────────▼───────────────────────────────────┐ │
│  │ Storage                                                    │ │
│  │   PostgreSQL 15（pgvector + tsvector + pg_partman 月分区） │ │
│  │   Redis 7（队列 / fan-out / 限流 / embedding cache）       │ │
│  │   MinIO / S3（大文本 / 导出产物 / 版本快照）                │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 与 digital_enterprise 的复用关系一览

| 子系统 | 在 digital_enterprise 中位置 | TokenKnows 处理方式 |
|---|---|---|
| CircuitBreaker / Retry / Bulkhead | `app/core/resilience.py`（244 行，0 依赖业务） | **直接复制** |
| 结构化日志 + Prometheus 指标 + OTel tracing | `app/core/observability/{metrics,middleware,tracing}.py` | **直接复制** |
| Redis 滑动窗口限流 | `app/core/rate_limiter.py` | **直接复制** |
| Embedding 缓存（SHA-256 + Redis） | `app/core/context_engine/embedding_cache.py` | **直接复制**，retarget 到 `value_segments` 与 `events.embeddings` |
| SSRF 防护 + 工具安全级别 | `app/core/security/` | **裁剪复用**（保 SSRF 部分，工具级别用不上） |
| LiteLLM 包装 + Provider Fallback 链 | `app/services/runtime/llm_client.py` | **改造复用**：在外层加 TokenKnows 的三层出域门禁 + egress_log |
| FastAPI Gateway 分层结构 | `gateway/ · schemas/ · services/ · repositories/ · domain/ · config/` | **借鉴目录结构** |
| Celery worker 入口与队列路由 | `app/workers/celery_app.py` | **借鉴启动模式**（队列名按 TokenKnows 改） |
| 两阶段任务执行（create → execute 后台） | `RuntimeService` 两段法 | **借鉴模式**，应用到文档生成 5 阶段流水线 |
| Pydantic Settings + 环境变量加载 | `app/config/settings.py` | **借鉴模板** |
| Alembic + asyncpg 工程化 | `migrations/` + `alembic.ini` | **借鉴配置**（含 sync psycopg2 driver for Alembic） |
| `pyproject.toml` 依赖清单 | `pyproject.toml` | **裁剪复用**（去掉 x402 / agentkit / web3 / coinbase / mattermost / feishu） |
| Mypy ratchet 协议 | `pyproject.toml` Phase B | **借鉴**（新文件 strict、旧文件 ignore） |
| **不复用**：blockchain（x402/agentkit/contracts/web3） | `core/x402/ · core/agentkit/ · core/contracts/` | TokenKnows 完全不需要 |
| **不复用**：IM channel pipeline（Feishu/Mattermost 双向） | `services/channel_*` | TokenKnows 只需"发布到 IM"单向，自己写 |
| **不复用**：coding agent / sandbox | `core/coding_agent/ · core/sandbox/` | TokenKnows 不执行代码 |
| **不复用**：workflow DAG engine | `services/workflow_orchestrator.py` | TokenKnows 用固定 5 阶段生成流水线 |
| **不复用**：marketplace / economics | `domain/marketplace/ · domain/economics/` | 与产品无关 |

> **复用边界总结**：digital_enterprise 的 `core/` 基础设施 ≈ 1/3 直接搬，`core/` 的其余部分按需借鉴；`gateway/schemas/services/repositories/domain` 的目录结构与命名约定**全盘借鉴**；业务领域代码 0 复用（产品定位完全不同）。

---

## 3. 技术栈

### 3.1 后端 Python 栈（已确认）

| 类别 | 选型 | 复用 digital_enterprise |
|---|---|---|
| 语言 | Python **3.12**（与 digital_enterprise 对齐，便于代码迁移） | — |
| Web | FastAPI ≥ 0.115 + uvicorn ≥ 0.32 + websockets ≥ 14 | ✅ |
| ORM | SQLAlchemy 2.x async + asyncpg + Alembic + psycopg2-binary（Alembic 用） | ✅ |
| DB | PostgreSQL 15 + pgvector ≥ 0.3.6 + tsvector + pg_partman（月分区） | ✅ |
| 队列 | Celery 5.4 + Redis 7（`[hiredis]`） | ✅ |
| LLM | **LiteLLM** ≥ 1.50（统一 4 厂商接口）+ openai ≥ 1.55（仅 embedding） | ✅ |
| 鉴权 | PyJWT[crypto]（RS256） + passlib[bcrypt]（**MVP 用 Argon2id**，需额外加 `argon2-cffi`） | 部分 ✅ |
| 配置 | pydantic ≥ 2.10 + pydantic-settings ≥ 2.6 | ✅ |
| 对象存储 | boto3（S3 / MinIO 共用） | ✅ |
| 可观测 | OpenTelemetry + structlog ≥ 24.4 + Prometheus exporter | ✅ |
| 文档解析 | pypdf ≥ 5.1 + python-docx ≥ 1.1 + pymupdf ≥ 1.24（**AGPL，注意商业分发**） | ✅ |
| 测试 | pytest ≥ 8.3 + pytest-asyncio + pytest-cov + testcontainers | ✅ |
| Lint | ruff ≥ 0.8 + mypy ≥ 1.13（strict） | ✅ |

### 3.2 前端栈（已 bootstrap）

| 类别 | 选型 | 状态 |
|---|---|---|
| 框架 | React 19 + TypeScript + Vite 8 | ✅ 已装 |
| 样式 | Tailwind CSS v4 + shadcn/ui + 自定义 token | ✅ 已装 |
| 状态 | Zustand 5 + TanStack Query 5 | ✅ 已装 |
| 路由 | React Router v7 | ✅ 已装 |
| 表单 | react-hook-form + zod | ✅ 已装 |
| 富文本 | TipTap v3 + StarterKit + Link + Placeholder + **自定义 Evidence mark** | ✅ 已装 |
| 抽屉/Drawer | vaul | ✅ 已装 |
| 图标 | lucide-react | ✅ 已装 |
| Mock | **MSW**（开发期前后端解耦） | ❌ **待加** |
| E2E | Playwright | ❌ 待加 |

### 3.3 不引入的依赖（避免膨胀）

- 不引入 GraphQL（REST + SSE 足够 MVP）
- 不引入 NATS（Redis Stream 单组件覆盖）
- 不引入 Elasticsearch（pgvector + tsvector 在 1M 事件量级够用，已验证可达 50ms P95）
- 不引入 Node 后端（Python 一统）
- 不引入额外 UI 库（Ant Design / MUI / Chakra）

---

## 4. 后端服务架构（详细）

### 4.1 进程划分

| 进程 | 镜像 | 职责 | 副本 | WORKER_QUEUES |
|---|---|---|---|---|
| `web` | `tokenknows/web` | 静态资源（Vite build 产物 + nginx） | 1-2 | — |
| `api` | `tokenknows/api` | REST + SSE + OpenAPI + 鉴权 | 2+ | — |
| `worker-ingest` | `tokenknows/worker` | 插件批量入库 + GitHub 轮询 / webhook + embedding 计算 | 1-2 | `ingest,embed` |
| `worker-extract` | `tokenknows/worker` | 价值识别（规则 + LLM 双层） | 2+ | `extract` |
| `worker-generate` | `tokenknows/worker` | 文档生成 + 脱敏识别 + 自评 | 2+ | `generate,redact` |
| `worker-publish` | `tokenknows/worker` | 外发飞书 / Slack / Notion + 导出 md/docx/pdf | 1 | `publish,export` |

> Worker 是**同一份镜像**，通过 `WORKER_QUEUES=ingest,extract` 决定订阅哪些队列。Compose 默认全订阅，K8s 分 Deployment 拆细。

### 4.2 目录布局（借鉴 digital_enterprise，**TokenKnows 业务化**）

```
tokenknows-api/
├── pyproject.toml
├── alembic.ini
├── migrations/                    # Alembic versions
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.worker
└── app/
    ├── main.py                    # FastAPI lifespan + 路由挂载
    ├── config/
    │   ├── settings.py            # pydantic-settings（借鉴 DE 模板）
    │   ├── database.py            # async engine + Redis client
    │   └── logging.py             # structlog 配置
    ├── core/                      # 基础设施（多个直接来自 DE）
    │   ├── resilience.py          # ← 复制自 DE
    │   ├── rate_limiter.py        # ← 复制自 DE
    │   ├── observability/
    │   │   ├── metrics.py         # ← 复制自 DE
    │   │   ├── middleware.py      # ← 复制自 DE
    │   │   └── tracing.py         # ← 复制自 DE
    │   ├── security/              # ← 复制 SSRF 部分自 DE
    │   ├── vault.py               # 简易 vault（sqlite + libsodium）
    │   ├── license.py             # 凭证验签
    │   └── embedding_cache.py     # ← 复制自 DE/core/context_engine
    ├── llm_gateway/               # ★ TokenKnows 核心，新写
    │   ├── interface.py           # LLMTask / LLMMessage / LLMResponse 协议
    │   ├── router.py              # 适配器选择 + 三层出域门禁
    │   ├── audit.py               # egress_log 写入
    │   └── adapters/
    │       ├── base.py            # BaseAdapter ABC
    │       ├── anthropic.py
    │       ├── openai.py
    │       ├── ollama.py
    │       └── vllm.py
    ├── gateway/                   # FastAPI 路由层
    │   ├── http_api/
    │   │   ├── auth.py
    │   │   ├── projects.py
    │   │   ├── members.py
    │   │   ├── datasources.py
    │   │   ├── ingestion.py
    │   │   ├── events.py
    │   │   ├── assets.py
    │   │   ├── generation.py
    │   │   ├── evidence.py
    │   │   ├── review.py
    │   │   ├── redaction.py
    │   │   ├── publish.py
    │   │   ├── audit.py
    │   │   └── admin.py           # 实例管理员
    │   ├── sse_api/
    │   │   ├── events_stream.py   # SSE 事件流
    │   │   └── generation_stream.py  # 生成 5 阶段进度
    │   └── auth_middleware.py
    ├── schemas/api/               # Pydantic 请求/响应模型
    ├── services/                  # 业务编排
    │   ├── auth_service.py
    │   ├── project_service.py
    │   ├── ingestion_service.py
    │   ├── extraction_service.py
    │   ├── generation_service.py  # 5 阶段流水线
    │   ├── evidence_service.py
    │   ├── redaction_service.py
    │   ├── publish_service.py
    │   └── audit_service.py
    ├── repositories/              # 数据访问（async SQLAlchemy）
    ├── domain/                    # ORM 模型按 bounded context 组织
    │   ├── user/
    │   ├── project/
    │   ├── datasource/
    │   ├── event/
    │   ├── value_segment/
    │   ├── asset/                 # asset + chapter + evidence + publish_record
    │   ├── redaction/
    │   └── audit/
    ├── workers/
    │   ├── celery_app.py          # 借鉴 DE
    │   ├── ingest_tasks.py
    │   ├── extract_tasks.py
    │   ├── generate_tasks.py
    │   └── publish_tasks.py
    └── tests/
        ├── unit/
        ├── integration/
        └── e2e/
```

### 4.3 关键数据流

#### 4.3.1 数据流 1 · 采集 → 入库

```
插件 batch (≤ 50 events)
  → POST /api/v1/ingestion/events
  → Bearer connection_token 校验 (project_id 隐含)
  → 写 events 表 (ON CONFLICT 唯一索引 DO NOTHING)
  → 投 ingest 队列 (后置 hash / embedding)
  → 同步 publish Redis "events.{project_id}" → SSE fan-out 工作台
返回 { accepted: N, rejected: [{external_id, reason}] }
```

#### 4.3.2 数据流 2 · 价值识别（增量 + 回扫）

```
events 入库 → trigger 投 extract 队列
  ├─ Step 1: 规则层（正则 + 关键词 + event_type）→ category candidate
  ├─ Step 2: LLM 层 Gateway.generate(task="value_extraction") → 8 分类
  └─ Step 3: 写 value_segments (event_id, span, category, trust_score)
trust_score 加权公式：
  source_authority(0.3) × corroboration(0.2) × recency(0.2) × extraction_confidence(0.3)
manual_trust_override（用户标记）永远覆盖自动分。
```

#### 4.3.3 数据流 3 · 文档生成（5 阶段流水线，对应要素 #8）

```
用户/定时触发 → POST /api/v1/projects/{id}/assets/generate
  → 创建 Asset(draft) + 投 generate 队列 + 返回 asset_id
异步 5 阶段（每阶段 publish Redis → 前端 SSE 收到进度）：
  ① collect:    候选 ValueSegment（按时间窗 + filter + trust_score TOP-N）
  ② outline:    主题聚类 + 大纲（LLM call 1，结构化输出 chapters[]）
  ③ content:    章节正文生成（LLM call × N，要求结构化引用 spans→event_ids）
  ④ evidence:   结构化引用回填 Evidence；失败回退 TF-IDF / pgvector cosine
  ⑤ assess:     自评卡（coverage / citation_density / slop_score / similarity）
=> Asset.status = draft (用户首次可见时)
```

#### 4.3.4 数据流 4 · 发布

```
Editor 提交 → asset.status = in_review
  → SSE/邮件通知 Reviewers
Reviewer 章节级 approve / reject
  → 全 approved AND 全 redacted_spans.status ∈ {confirmed,overridden,exempted}
  → "发布"按钮在前端激活
点击发布
  → publish_service:
    ├─ 创建 PublishRecord(status=pending)
    ├─ Asset.current_version++ 冻结快照（chapters 含 layout/redacted_spans 不可变）
    │   Evidence 携带 event_version
    └─ 投 publish 队列：导出（md/docx/pdf）或推送（飞书/Slack/Notion）
  → 完成后 PublishRecord.status = success/failed
```

---

## 5. LLM Gateway 与三层出域门禁（**核心，详细**）

这是整个产品**对外承诺最强**的部分：默认零出域 + 客户密钥客户管 + 完整出域审计。`Pitch §5.1` 是给客户法务看的合规话术，这里给的是它如何在代码里成立。

### 5.1 接口定义（新写，不直接复用 DE）

```python
# app/llm_gateway/interface.py
from typing import Literal, Protocol, AsyncIterator
from pydantic import BaseModel
from uuid import UUID

LLMTask = Literal[
    "value_extraction",      # B 模块
    "weekly_report",         # C1
    "tech_design",           # C2
    "adr",                   # C3
    "incident",              # C4
    "redaction_llm",         # F1 LLM 层
    "evidence_match",        # D1 启发式回退
]

class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class LLMOptions(BaseModel):
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    json_mode: bool = False
    timeout_seconds: float = 120

class LLMResponse(BaseModel):
    text: str
    usage: dict
    model_used: str
    provider: str
    latency_ms: int
    fallback_used: bool = False
    egress_blocked: bool = False    # True 表示因门禁降级到 local

class LLMGateway(Protocol):
    async def generate(
        self, task: LLMTask, messages: list[LLMMessage],
        options: LLMOptions, project_id: UUID, user_id: UUID | None = None,
    ) -> LLMResponse: ...
    async def stream(
        self, task, messages, options, project_id, user_id=None,
    ) -> AsyncIterator[str]: ...
```

### 5.2 适配器（4 个）

复用思路：**底层包 LiteLLM**（让 LiteLLM 处理 Anthropic / OpenAI / Ollama / vLLM 的协议差异），TokenKnows 只在外层加 **task→model 映射 + 出域门禁 + 审计**。

```python
# app/llm_gateway/adapters/base.py
class BaseAdapter(ABC):
    provider: str
    is_cloud: bool   # True for anthropic/openai; False for ollama/vllm

    @abstractmethod
    async def generate(self, messages, options) -> LLMResponse: ...
    @abstractmethod
    async def stream(self, messages, options) -> AsyncIterator[str]: ...
```

四个适配器在 `app/llm_gateway/adapters/{anthropic,openai,ollama,vllm}.py`。每个适配器内部都用 LiteLLM 的 `acompletion()`，**不直接 `import anthropic`**。这样 4 个文件总共可能就 < 300 行。

### 5.3 三层出域门禁实现

```python
# app/llm_gateway/router.py
class LLMRouter:
    async def select_adapter(
        self, task: LLMTask, project_id: UUID
    ) -> BaseAdapter:
        # 1. 读 task→provider 映射（项目级 task_egress_config 覆盖 / 实例级 default）
        primary = self._lookup_primary(task, project_id)

        # 2. cloud adapter 必须过三层门禁
        if primary.is_cloud:
            if not await self._egress_allowed(task, project_id):
                local = self._lookup_fallback_local(task, project_id)
                if local is None:
                    raise EgressDeniedError(task, project_id)
                return local
        return primary

    async def _egress_allowed(self, task, project_id) -> bool:
        # 三层 AND，任一 OFF 即拒绝
        instance = await self.settings.get("instance_egress_enabled", False)
        if not instance: return False

        project = await self.db.get_project(project_id)
        if not project.llm_egress_enabled: return False

        return project.task_egress_config.get(task, False)
```

### 5.4 调用全流程（含审计）

```python
# app/llm_gateway/router.py
async def generate(
    self, task, messages, options, project_id, user_id=None
) -> LLMResponse:
    adapter = await self.select_adapter(task, project_id)
    breaker = get_circuit_breaker(f"llm-{adapter.provider}")  # 复用 DE/core/resilience

    start = time.monotonic()
    try:
        result = await breaker.call(adapter.generate, messages, options)
    except (CircuitOpenError, AdapterError) as e:
        # 尝试 fallback 链（同 provider 内的备用模型 → 跨 provider）
        fallback = self._next_fallback(task, project_id, exclude=[adapter.provider])
        if fallback is None: raise
        result = await fallback.generate(messages, options)
        result.fallback_used = True
        adapter = fallback

    result.latency_ms = int((time.monotonic() - start) * 1000)

    # cloud adapter 强制写出域审计
    if adapter.is_cloud:
        await self.audit.record_egress(
            project_id=project_id, user_id=user_id, task=task,
            provider=adapter.provider, model=result.model_used,
            messages=messages, response=result,
        )
    return result
```

### 5.5 与 digital_enterprise `llm_client.py` 的对比

| 维度 | digital_enterprise `LLMClient` | TokenKnows `LLMGateway` |
|---|---|---|
| 抽象层级 | 业务层直接调 `LLMClient(model=...)` | 业务层只调 `gateway.generate(task=...)`，model 由 router 决策 |
| 出域控制 | 无 | **三层门禁强制** |
| 审计 | 写 cost_ledger（按 USDC 计价） | 写 egress_log（不含成本，只审计出域行为） |
| Fallback | LiteLLM 内置 fallback_models | TokenKnows router 主导，记录 fallback_used 用于 UI 标"由 X 模型生成" |
| Streaming | `astream_chat()` | `gateway.stream()`，SSE 直传前端 |

**结论**：DE 的 `LLMClient` **不直接复用**，但其"用 LiteLLM 包装 + Provider Fallback + Token usage 统计"的实现思路**完全借鉴**。Gateway 自己写约 400-500 行 Python，且会随着 task 数量稳定（MVP 7 个 task）。

### 5.6 强制约束（CI 闸口）

在 `pyproject.toml` 加 ruff rule：

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"anthropic".msg = "Use app.llm_gateway instead"
"openai.OpenAI".msg = "Use app.llm_gateway instead"
"openai.AsyncOpenAI".msg = "Use app.llm_gateway instead"
"ollama".msg = "Use app.llm_gateway instead"
# 例外：app/llm_gateway/adapters/ 内可以 import，需要在文件头 # noqa: TID251
```

CI workflow 跑 `ruff check app/`，违反直接挂。

---

## 6. 价值识别与证据链（详细）

### 6.1 价值识别双层引擎

| 层 | 实现 | 何时跑 |
|---|---|---|
| 规则层 | 正则 + 关键词 + event_type + author 权重 | 入库即时（同步） |
| LLM 层 | `gateway.generate(task="value_extraction")` + 8 分类 prompt + JSON mode | 异步批，超长事件分块 |

**8 个分类**：`architecture_decision / bug_rca / prompt_pattern / tech_design / performance / security / ux_feedback / other`

**输出**：`ValueSegment(event_id, span_start, span_end, category, trust_score, category_confidence, manual_trust_override)`。

**`trust_score` 加权公式**（PRD §5.2 B2）：
```
trust_score =
    0.3 × source_authority(event)        # PR 合并 > Issue 关闭 > 讨论 > 聊天
  + 0.2 × corroboration(event)           # 被多少独立来源印证
  + 0.2 × recency(event)                 # 时间衰减（30d 半衰期）
  + 0.3 × extraction_confidence(LLM)
```

`manual_trust_override ∈ {1, -1, null}` 由用户标记，**永远覆盖**自动分。

### 6.2 证据链生成与漂移管理（PRD §5.4 D1）

**生成期**：要求 LLM 在 chapter generation prompt 里结构化输出引用：
```json
{
  "chapter_id": "...",
  "spans": [
    {"text": "...", "supports": ["evt_uuid1", "evt_uuid2"]}
  ]
}
```

LLM 失败 / 返回非结构化 → 回退 `task="evidence_match"` 启发式：TF-IDF + pgvector cosine ≥ 0.7 的事件作为 candidate evidence。

**编辑期漂移**：
| 编辑后内容相似度 | 行为 |
|---|---|
| ≥ 70% | 保留 Evidence |
| 30%–70% | `stale=true`，UI 黄色提示 |
| < 30% 或删除 | 移除 Evidence |

字符相似用 `difflib.SequenceMatcher.ratio()` 或 normalized Levenshtein。

**版本快照**：发布时 Evidence 携带 `event_version`；PR 后续被改不会让引用漂移。

---

## 7. 实时事件流（SSE 主路径）

### 7.1 前后端协议

| 端点 | 协议 | 用途 |
|---|---|---|
| `/api/v1/ws/projects/{id}/events` | SSE | 工作台事件流 fan-out |
| `/api/v1/ws/assets/{id}/generation` | SSE | 文档生成 5 阶段进度 |
| `/api/v1/ws/projects/{id}/editor/{chapter_id}` | WebSocket | 编辑器章节级锁定通知（仅这一处用 WS） |

### 7.2 后端实现

```python
# app/gateway/sse_api/events_stream.py
from sse_starlette.sse import EventSourceResponse

@router.get("/ws/projects/{project_id}/events")
async def stream_project_events(project_id: UUID, ...):
    channel = f"events.{project_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async def event_generator():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                yield {"event": "event", "data": msg["data"]}
    return EventSourceResponse(event_generator())
```

入库 worker 写完 events 表后 `redis.publish("events.{project_id}", json.dumps({...}))` → 所有订阅该项目的 SSE 客户端收到。

### 7.3 前端实现（任务 T03 内）

```typescript
// src/features/workbench/hooks/useEventStream.ts
// MVP 阶段：polling 30s（任务包要求），第 4 周替换为 SSE
export function useEventStream(projectId: string) {
  const queryClient = useQueryClient();
  // SSE 替换点 START
  useInterval(() => {
    queryClient.invalidateQueries(['projects', projectId, 'events']);
  }, 30_000);
  // SSE 替换点 END
}
```

**注意**：Vite dev server 默认 proxy 会掐 SSE。`vite.config.ts` 需要：
```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      // 关键：禁用 buffering，否则 SSE 断流
      configure: (proxy) => {
        proxy.on('proxyReq', (proxyReq) => {
          proxyReq.setHeader('X-Accel-Buffering', 'no');
        });
      },
    },
  },
}
```

---

## 8. 脱敏门禁（发布闸）

### 8.1 双层识别

| 层 | 引擎 | 适用对象 |
|---|---|---|
| 规则层 | 正则 + 内建敏感清单（API Key / URL / Token / 邮箱 / IP / 信用卡 / 企业域名） | 高确定性 |
| LLM 层 | `gateway.generate(task="redaction_llm")` JSON 输出 | 客户名 / 内部系统名 / 未发布功能 |
| 项目自定义层 | 项目级 `custom_redaction_terms`（正则列表） | 客户专属 |

合并优先级：**自定义 > 规则 > LLM**。

### 8.2 强制门禁

```python
# 发布 service 内
async def can_publish(asset_id) -> tuple[bool, str]:
    asset = await db.get_asset(asset_id)
    if asset.approval_state != "approved":
        return False, "审批未通过"

    chapters = await db.list_chapters(asset_id, version=asset.current_version)
    for ch in chapters:
        for span in ch.redacted_spans:
            if span["status"] not in {"confirmed", "overridden", "exempted"}:
                return False, f"还有未确认敏感项: chapter {ch.order_index}"
    return True, ""
```

前端发布按钮 disabled，Tooltip 显示"还有 N 处未确认"。

### 8.3 原文不入库

`Chapter.redacted_spans[*]`：
```ts
{
  span_start: int,
  span_end: int,
  type: "CUSTOMER" | "API_KEY" | "INTERNAL_SYSTEM" | "EMAIL" | "IP" | "CUSTOM_<name>",
  status: "pending" | "confirmed" | "overridden" | "exempted",
  original_hash: string,  // SHA256(original_text)，仅审计用
  applied_text: string,   // 替换后的文本（占位符或用户自定义）
}
```

**原文从不持久化**，只留 hash。即便数据库被脱库，敏感项也不会泄漏。

---

## 9. 数据库 Schema（关键表）

完整 DDL 见 TDD §5；这里仅列**该项目独有 / 高风险**字段，并提示索引。

| 表 | 关键字段 | 索引 |
|---|---|---|
| `users` | id / email / password_hash(**Argon2id**) / is_instance_admin / locked_until / failed_login_count | UNIQUE(email) |
| `projects` | id / owner_id / **llm_egress_enabled** / **task_egress_config**(JSONB) / custom_redaction_terms / brand_theme | — |
| `instance_settings` | key / value(JSONB) — 含 `instance_egress_enabled` | PK(key) |
| `project_members` | project_id / user_id / role∈(owner,editor,reviewer,viewer) | PK 复合 |
| `events` | project_id / source_type / source_ref / external_id / version / event_type / content / payload / content_blob_ref / **embeddings vec(1536)** / content_hash | **UNIQUE 四元组**, GIN(tags), ivfflat(embeddings), `按 occurred_at 月分区` |
| `value_segments` | event_id / span_start / span_end / category / trust_score / manual_trust_override / extraction_state | (event_id), (trust_score DESC) |
| `assets` | type / status∈(draft,in_review,approved,published,archived) / current_version / approval_state / redaction_state / metrics | — |
| `chapters` | asset_id / **asset_version** / order_index / content / content_blob_ref / layout(JSONB) / generated_by / regeneration_history(JSONB) / **redacted_spans**(JSONB) | UNIQUE(asset_id, asset_version, order_index) |
| `evidences` | chapter_id / event_id / **event_version** / span / citation_text / manually_added / stale | (chapter_id), (event_id) |
| `publish_records` | asset_id / asset_version / destination∈(internal,feishu,slack,notion,export_pdf,export_docx,export_md) / status / url | — |
| `audit_log` | ts / user_id / project_id / action / resource_type / resource_id / diff(JSONB) / ip | (project_id, ts DESC), (user_id, ts DESC) |
| `egress_log` | ts / project_id / user_id / task / provider / model / sizes / tokens / latency_ms / cost_estimate / hash_of_request | (project_id, ts DESC) |

**两个 inline 阈值**：
- `events.content` ≥ 32KB → 写 MinIO，DB 留 `content_blob_ref`
- `chapters.content` ≥ 64KB → 同上，DB 留 `content_blob_ref`

> Chapter 阈值更高的原因（TDD §7.2.5）：Chapter 在文档预览、编辑、审批、导出时被频繁全文读取；Event 主要被价值识别批处理读取，频次低很多。

---

## 10. 前端架构 × 任务包映射

### 10.1 路由 / Feature 模块（与 15 个任务一一对应）

| 路由 | Feature 目录 | 任务包 | 关键依赖 |
|---|---|---|---|
| `/login` `/register` `/verify-email` `/forgot-password` `/reset-password` | `features/auth` | **T01** | authStore + api.ts + zod |
| `/projects/new` | `features/projects/wizard` | **T02** | 4 步向导 + connection token 生成 |
| `/` `/projects/:id` | `features/workbench` | **T03** | SSE/polling + 事件流 + 三栏 |
| `/projects/:id/events/:eid` (drawer) | `features/events` | **T04** | shadcn Sheet |
| `/projects/:id/documents` | `features/documents/list` | **T05** | 触发生成 + 卡片网格 + progress |
| `/projects/:id/documents/:docId` | `features/documents/page` | **T06** | TipTap + auto-save + IntersectionObserver |
| (drawer 内) | `features/documents/evidence` | **T07** | 抽屉 + 角标联动 |
| (modal 内) | `features/documents/regenerate` | **T08** | LLM 选择 + instruction |
| `/projects/:id/documents/:docId/review` | `features/review` | **T09** | 章节级 approve/reject + 批注 thread |
| `/projects/:id/documents/:docId/redaction` | `features/redaction` | **T10** | scan polling + 分组 |
| (modal 内) | `features/publish/dialog` | **T11** | 多渠道选择 + 导出 |
| `/projects/:id/documents/:docId/receipt` | `features/publish/receipt` | **T12** | 版本 diff |
| `/projects/:id/settings` | `features/settings` | T13（v0.2） | — |
| `/projects/:id/settings/llm` | `features/settings/llm` | T14（v0.2） | **三层开关 UI** |
| `/admin/*` | `features/admin` | T15（v0.2） | 实例管理员 |

### 10.2 状态分层准则（强约束）

| 状态类型 | 工具 | 例子 | 禁忌 |
|---|---|---|---|
| 服务端数据 | **TanStack Query** | 项目列表 / 事件流 / 文档详情 | **永远不塞进 Zustand** |
| 跨页 UI | Zustand | currentProject / sidebar 开合 / docUiStore（drawer 状态） | — |
| 本页临时 | useState | 表单字段、悬停态 | 不要过度抽象 |
| token / 用户 | Zustand + localStorage(`tokenknows_auth`) | authStore | — |

### 10.3 通用 UI 状态契约（每屏 4 态）

所有调接口组件**必须有**：Loading（Skeleton 骨架）/ Empty（EmptyState 组件 + 主操作）/ Error（重试按钮）/ Success。由 `src/components/shared/{EmptyState,ErrorState,Skeleton}.tsx` 提供。任务包 T01-T15 均已列入验收。

### 10.4 颜色 token 强约束

Tailwind class 必须用 `bg-bg-card text-text-primary border-border-subtle` 等自定义 token，**禁止 `bg-stone-50` 等原生色**。完整清单在 `tailwind.config.ts`，配色源 [DesignHandoff §2.1](../DesignHandoff_TokenKnows_MVP.md)。

---

## 11. 部署架构（双形态 / 同一份代码）

### 11.1 Compose 简易版

`docker-compose.yml` 拉起 6 个容器：postgres / redis / minio / api / worker / web。所有配置走环境变量。`setup.sh` 引导生成密码、license 验签、首次迁移、健康检查。**目标 30 分钟内上线**。

资源估算（Pitch §6.1）：
| 用户 | CPU | RAM | 磁盘 |
|---|---|---|---|
| 3-10 人 | 4 vCPU | 16GB | 100GB SSD |
| 10-30 人 | 8 vCPU | 32GB | 250GB SSD |

### 11.2 K8s Helm 企业版

```
charts/tokenknows/
├── Chart.yaml
├── values.yaml                # 开发默认
├── values-prod-example.yaml   # 生产参考（外置 PG/Redis/S3）
├── templates/
│   ├── deployment-api.yaml
│   ├── deployment-worker-{ingest,extract,generate,publish}.yaml
│   ├── deployment-web.yaml
│   ├── service-*.yaml
│   ├── ingress.yaml
│   ├── secret-{db,llm,license}.yaml
│   ├── configmap.yaml
│   ├── pdb.yaml               # PodDisruptionBudget
│   └── hpa.yaml               # HorizontalPodAutoscaler
└── charts/                    # 可选子 chart：bundled pg/redis/minio
```

**外置依赖（生产推荐）**：
```yaml
postgres:
  bundled: false
  url: "postgresql+asyncpg://..."
redis:
  bundled: false
  url: "redis://..."
objectStorage:
  bundled: false
  endpoint: "https://s3.amazonaws.com"
  bucket: "tokenknows-prod"
```

### 11.3 唯一差异点

| 差异 | Compose | K8s |
|---|---|---|
| 配置加载 | `.env` | Helm values + ConfigMap |
| 数据存储 | bundled | 外置 |
| HA | 单点 | 多副本 + PDB |
| 监控 | Prometheus / Grafana 单容器（可选） | 与客户现有 Prometheus 集成 |

**业务代码 0 差异**。

### 11.4 升级与 License

- 镜像版本化 SemVer
- 启动时 `alembic upgrade head`，失败 exit ≠ 0 → K8s 自动回滚到上一稳定 Pod
- Major 升级提供 dry-run 脚本：`alembic upgrade --sql > migration.sql`
- License：`tokenknows.license` 凭证文件（RSA-4096 + PKCS1v15 + SHA256 验签），过期进入只读模式（已采数据可看，不可新生成）

---

## 12. 可观测性与运维（**直接复用 DE/core/observability**）

| 能力 | 实现 | 来源 |
|---|---|---|
| 结构化日志 | structlog JSON + Trace ID 全链路注入 | ✅ 复制 `DE/core/observability/middleware.py` |
| 指标接口 | Prometheus `/metrics` + `prometheus_fastapi_instrumentator` | ✅ 复制 `DE/core/observability/metrics.py` |
| 链路追踪 | OpenTelemetry SDK + Jaeger 协议 | ✅ 复制 `DE/core/observability/tracing.py` |
| 健康检查 | `/healthz`（存活）+ `/readyz`（含 DB/Redis/MinIO ping） | 新写（小） |
| Grafana 面板 | 2 份模板（ops + business） | 新写 |
| 告警 | Prometheus alert rules：采集断连 / 生成超时 / LLM 异常 / 磁盘 | 新写 |

**业务埋点**（PRD §6.3）：
- 数据接入：每数据源采集成功率 / 事件总数 / 延迟分布
- 文档生成：生成时延 / 模型耗时 / Token 用量 / 自评分布 / 人工修改率
- 发布：发布数 / 按目的地分布 / 撤回率
- 脱敏：识别命中数 / 误报率（用户标"非敏感"的占比）
- **出域**：项目级 / 实例级 token 用量看板（来自 `egress_log`）

---

## 13. 安全与合规

### 13.1 强制基线（PRD §6.2 / Pitch §5.7）

| 项 | 实现 |
|---|---|
| 传输加密 | HTTPS / TLS 1.2+，禁弱密码套件，HSTS |
| 静态加密 | Postgres + MinIO AES-256；vault 二次加密敏感字段 |
| 密码哈希 | **Argon2id**（`memory_cost=64MB, time_cost=3, parallelism=1`） |
| 密码策略 | ≥ 10 位、含字母+数字+符号；5 次失败锁 15 分钟 |
| JWT | RS256，access 15min / refresh 7d |
| 公私钥 | 实例首启动生成 4096-bit RSA，存 vault |
| 简易 vault | sqlite + libsodium SecretBox；master key 来自启动 env |
| 企业 vault | 可选外接 HashiCorp Vault / AWS KMS |
| CSRF/XSS/SQLi | FastAPI 默认防护 + Pydantic 校验 + SQLAlchemy 参数化 |
| 依赖漏洞 | CI 跑 SCA + bandit（Python） + trivy（镜像） |
| 渗透测试 | OWASP Top 10 全部通过 |
| 审计保留 | ≥ 90 天 |

### 13.2 二次确认动作

数据源删除、外部发布、修改 LLM 出域开关、修改自定义敏感词清单——所有这些动作必须前端二次确认弹窗 + 后端写 audit_log。

### 13.3 紧急关停

实例管理员可一键关闭所有出站连接，进入"全离线模式"。全离线下仍可生产使用（本地 LLM），仅不能云端 LLM / 自动更新。

---

## 14. 测试策略

| 类型 | 工具 | 触发 | 目标 |
|---|---|---|---|
| 单元 | pytest + pytest-asyncio | 每 PR | 行覆盖 ≥ 70%（新代码 strict） |
| 集成 | pytest + testcontainers | 每 PR | 关键路径 happy + edge |
| 前端单元 | vitest + react-testing-library | 每 PR | 组件覆盖 ≥ 60% |
| E2E | Playwright | nightly | 8-10 个核心 user flow |
| 性能 | k6 | 每 Sprint 末 | PRD §6.1 SLA |
| 安全 | trivy / bandit / npm audit | 每 PR | 阻塞高危 CVE |
| LLM 输出回归 | 自研 + golden set（100 条） | 模型 / Prompt 变更 | coverage / citation_density / slop_score drift |

**Mypy ratchet**（借鉴 DE 模式）：新文件 strict、旧文件 ignore，逐步推进。

---

## 15. 里程碑拆解（**双轨**）

> 这一节是本文档最大的"新增价值"。`engineering_handoff/README.md` 是"4 周 solo 演示版"路径，PRD §11 是"12 周 6 Sprint 试点版"路径。两条路径互补、不冲突，下面把两条线和它们的衔接讲清。

### 15.1 Track A · 演示版（4 周 / Solo / 全 MSW mock）

**目标**：可走 demo 给意向客户的前端 MVP，前后端完全解耦。**目标产物：5 分钟演示视频**。

| 周 | 重点 | 出口闸 |
|---|---|---|
| W1 | bootstrap + AppLayout + 通用 Empty/Error/Skeleton + T01 auth + T02 项目向导 | 录屏：注册 → 建项目 → 看工作台 |
| W2 | T03 工作台（polling） + T05 文档列表 + **T06 三栏布局 / TipTap / 自动保存** | 录屏：打开 mock 文档 → 改 → 看证据 → 重生成 |
| W3 | T07 证据抽屉 + T08 重生成 + T04 事件详情 + T09 审批 + T10 脱敏 + T11/T12 发布回执 | 录屏：一篇文档 30 分钟走完 编辑→审批→脱敏→发布 |
| W4 | 接真后端联调 + SSE 替换 polling + Playwright e2e + UI 打磨 + 录 5 分钟 demo 视频 | demo 视频可发客户 |

**里程碑 M-A1（W4 末）**：v0.1 演示版上线候选 — 内部装一台演示环境，3 分钟从零走完全链路。

> 不能砍的：T01 / T02 / T03 / T05 / T06 / T07 / T11 / T12。8 屏砍掉任何一个都跑不通主链路（README 已明确）。

### 15.2 Track B · 试点版（12 周 / 全栈 / 真私有化）

PRD §11 已定义 6 Sprint。下表把 Track A 的前端产出与 Track B 的后端 Sprint 对齐：

| Sprint | 周 | 后端交付 | 前端交付（接真后端） | LLM | 部署 | 出口闸 |
|---|---|---|---|---|---|---|
| **S1** | W1-2 | API 骨架（FastAPI + Alembic + 基础 middleware） · auth 全链路 · **LLM Gateway 接口 + Anthropic 适配器** | T01 + T02（连真后端） | Anthropic（仅内部） | Compose 单机可启动 | M0：开发自测可注册建项目 |
| **S2** | W3-4 | Claude Code 插件 · GitHub PAT · `/ingestion/events` · events SSE | T03 工作台 + T04 事件详情 | — | Compose 完整 | **M1（W4）内部 Demo Day** |
| **S3** | W5-6 | 价值识别双层 · 周报生成流水线 · 证据链 v1 · 自评卡 | T05 文档列表 + T06 编辑器 + T07 证据 + T08 重生成 | 周报走 Anthropic | — | 周报可生成，证据可看 |
| **S4** | W7-8 | 单级审批 · **Ollama 适配器** · ADR 模板 | T09 审批 | **Ollama 上线**（试点 gate） | — | **M2（W8）首家试点接入**（无外发） |
| **S5** | W9-10 | 双层脱敏 + 强制门禁 · md/docx/pdf 导出 · 飞书/Slack ≥ 1 · 技术方案/复盘模板 | T10 脱敏 + T11 发布 + T12 回执 | — | — | 一篇文档完整闭环（含外发） |
| **S6** | W11-12 | Cursor / VS Code 扩展 · 模板齐套 4 类 · 性能 / 安全扫描 | T13 / T14 / T15 | vLLM 适配（可选） | **K8s Helm Chart 完成** | **M3（W12）MVP v1.0**，3-5 家试点 |

**每 Sprint 必过的发布门禁**（PRD §11）：
- 单元 + 集成测试通过
- k6 跑 PRD §6.1 SLA（工作台 P95<2s / 生成 P95<60s / 实时 P95<5s）
- SCA + SAST + 镜像扫描无高危
- Demo Friday 内部演示

### 15.3 两轨衔接策略

| 衔接点 | 做法 |
|---|---|
| Solo 模式（前 4 周） | 跑 Track A，全 MSW mock；同时**只在 W2 末**搭后端骨架（4 小时）：建 `tokenknows-api` 仓库 + 复制 DE 的 `core/{resilience,observability,rate_limiter}.py` + Alembic + Auth |
| Track A W4 末交付完，看商业反馈 | 若签到试点客户 → 转 Track B，但 W5 起后端**已经有可用骨架** + 复制好的基础设施，可直接进 S3（不必从 S1 重新起步） |
| 若没签到客户 | 持续打磨 Track A 演示版 + 主动联系试点；Track B 不启动 |
| 若签到 > 1 家 | Track A 4 周完成后立即转 Track B，**前 4 周相当于 S1+S2 的前端部分提前完成**，整体可在 W12 前交付试点版 |

---

## 16. 风险与缓解（按高低排）

| 风险 | 严重度 | 缓解 | 备注 |
|---|---|---|---|
| AI 生成质量不达预期 | 高 | 自评卡（要素 #12） + 章节重生（#10） + 多模型切换（#11） + 试点共建 | 已在产品体验内置 |
| **Ollama 在 S4 之前没就绪 → M2 阻塞** | 高 | S2 起跟 Ollama 集成 spike；S3 先用 7B 模型跑 value_extraction 验证可用性 | M2 硬性 gate |
| Copilot Chat API 兼容性 | 中 | **S6 启动前必须有真实 API spike**；兜底剪贴板复制+手动绑定 | TDD §14 #2 |
| pgvector 在 1M+ 事件量级性能未实测 | 中 | S2-S3 间跑性能 spike；备用 `lists` 参数调优 / 切 HNSW | TDD §14 #1 |
| 私有化部署 IT 拒绝 | 高 | Compose 一键脚本 + 详细部署手册 + 远程协助；S1 末即可装 PoC | Pitch §6 已就绪 |
| Solo 节奏脱离 12 周计划 | 中 | Track A 4 周演示版可独立跑出来卖；先签客户、再排后端 | README 路径 |
| LLM 成本 / 出域审计漏写 | 高 | egress_log 设为 cloud adapter 调用强制 hook + CI 测试覆盖 | TDD §7.4 |
| 试点客户业务忙、试点拖延 | 中 | 试点合约明确双周节奏 + 共建顾问每周陪跑 1h | Pitch §7.4 |
| Celery 在私有化场景的运维复杂度 | 中 | 备选 ARQ / Dramatiq（更轻量）；MVP 阶段先用 Celery，S6 评估 | TDD §14 #3 |
| 简易 vault 不够企业级 | 中 | MVP 用 sqlite + libsodium；企业版允许接外部 vault（HashiCorp / KMS） | TDD §14 #5 |
| MinIO 在生产可靠性 | 低 | Compose 内置仅作 PoC；K8s 生产默认外置 S3 兼容存储 | TDD §14 #4 |

---

## 17. 复用工作 · 具体到文件级行动清单

下面这份清单是**给 Claude Code 直接执行的工程动作**，不需要再次决策。

### 17.1 立即可做（无依赖）

| 行动 | 源 | 目标 | 修改 |
|---|---|---|---|
| 创建 `tokenknows-api` 仓库 | — | `/Users/wujun/TokenKnows/code/tokenknows-api/` | 新建 |
| 复制 resilience 模块 | `DE/app/core/resilience.py` | `tokenknows-api/app/core/resilience.py` | 0 修改 |
| 复制 observability 三件套 | `DE/app/core/observability/{metrics,middleware,tracing}.py` | `tokenknows-api/app/core/observability/` | 0 修改 |
| 复制 rate_limiter | `DE/app/core/rate_limiter.py` | `tokenknows-api/app/core/rate_limiter.py` | 0 修改 |
| 复制 embedding_cache | `DE/app/core/context_engine/embedding_cache.py` | `tokenknows-api/app/core/embedding_cache.py` | 改 import 路径 |
| 复制 settings 模板 | `DE/app/config/settings.py` | `tokenknows-api/app/config/settings.py` | 删除业务字段，保留模式 |
| 复制 alembic 配置 | `DE/alembic.ini` + `DE/migrations/env.py` | `tokenknows-api/` 对应位置 | 改 DB URL 与 metadata import |
| 复制 ruff / mypy / pytest 配置 | `DE/pyproject.toml` 相关段 | `tokenknows-api/pyproject.toml` | 改 package name |

### 17.2 前端（在已有 `tokenknows-web` 内）

| 行动 | 状态 |
|---|---|
| 装 MSW：`npm i -D msw` + `npx msw init public/` | ❌ 待做 |
| 写 `src/mocks/handlers.ts`（按 TDD §6.1 端点） | ❌ 待做 |
| 写 `src/components/shared/{EmptyState,ErrorState,Skeleton}.tsx` 通用三态组件 | ❌ 待做（T01-T12 都依赖） |
| 在 `vite.config.ts` 加 SSE-friendly proxy 配置 | ❌ 待做 |

### 17.3 Sprint S1 前必须解决的开放问题

1. **试点客户首选哪一类 LLM**（Ollama 32B vs Anthropic Sonnet）？决定 S4 Ollama spike 规模
2. **飞书 / Slack / Notion 哪个是 S5 必做的目的地**？只做 1 个即可过 M3
3. **自定义敏感词清单的 UI 复杂度**：项目设置 v0.2 还是 S5 必做？
4. **是否使用 LiteLLM**（推荐）或自己写 4 个 SDK 适配器？LiteLLM 路径可省 200-300 行代码且与 DE 一致

---

## 18. 文档关系图

```
BRD（商业为什么） ─┐
                 ├──→ PRD（产品做什么 / 验收）
Pitch（怎么卖）  ─┘                  │
                                    ├──→ TDD（技术架构 / API / Schema）
DesignHandoff（怎么长） ─────────────┤
                                    │
                                    ├──→ Architecture.md（本文 / 施工动线 + 双轨里程碑 + 复用 DE）
                                    │                │
                                    │                ├──→ SharedFoundations.md（项目地基 · v0.2）
                                    │                │     ├── api.ts / stores / 三态组件 / 路由
                                    │                │     ├── 双 token 系统裁决 + 字体加载
                                    │                │     ├── i18n / a11y / 性能预算
                                    │                │     └── W1D1 地基日清单
                                    │                │
                                    │                └──→ TaskTechDesign.md（任务深化 · v0.2）
                                    │                      ├── T01-T15 关键决策与补充
                                    │                      ├── 跨任务衔接 contract
                                    │                      ├── Track A 4 周逐日补强
                                    │                      └── 全局质量门禁
                                    │
                                    └──→ engineering_handoff/
                                         ├── README.md（4 周 solo sprint）
                                         ├── 00-bootstrap.md（环境）
                                         ├── CLAUDE.md（AI 项目记忆）
                                         └── tasks/T01-T15.md（每屏施工包）
```

### v0.2 文档分工补注

本文档（Architecture.md）定位"宏观施工动线"——分层架构、双轨里程碑、digital_enterprise 复用清单、风险矩阵——稳定不动。

需要下钻到 `src/` 文件层级或每屏工程判断时，看：

| 你要找 | 看哪份 |
|---|---|
| `src/lib/api.ts` 长什么样、Zustand stores 字段、路由 + guard 结构、token 系统裁决、a11y 4 条硬指标 | [SharedFoundations.md](./SharedFoundations.md) |
| 某个任务（T0X）的关键技术决策、上下游 contract、已知坑工程补充、Track A 逐日时序 | [TaskTechDesign.md](./TaskTechDesign.md) |
| 后端进程划分、LLM Gateway 三层门禁、4 个数据流、复用清单、Sprint 级里程碑 | 本文档 |

**改动规则**：本文档不再扩 §17 之外的文件级清单；架构铁律变更才升 v0.3。下钻细节的迭代发生在 SharedFoundations / TaskTechDesign 内。

---

## 附录 A · 关键术语对照（避免歧义）

| 在 PRD/TDD 里 | 在 DE 里有对应 | 是否相同 |
|---|---|---|
| Asset / Chapter / Evidence | Task / Run / Cost — 不对应 | TokenKnows 独有 |
| Event（研发事件） | ChannelMessage / TaskArtifact — 部分类似但语义不同 | 不直接复用 |
| ValueSegment | MemorySemantic（pgvector）— 存储模式类似 | 借鉴存储设计 |
| LLM Gateway | LLMClient — 抽象差异大 | 借鉴 LiteLLM 包装，不复用 |
| egress_log | cost_ledger — 维度不同 | TokenKnows 独写 |
| Connection token（插件） | ExternalApiKey（A2A） | 借鉴 HMAC + 签名模式 |

## 附录 B · 文档版本历史

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v0.1 | 2026-05-20 | 初稿：架构总览 + 双轨里程碑 + DE 复用清单 + 文件级行动表 | John + Claude |
| v0.2 | 2026-05-20 | §18 文档关系图扩展 SharedFoundations.md / TaskTechDesign.md 两个节点 + 加分工补注 | John + Claude |

---

**下一步行动**（按优先级）：

1. ✅ 落本文档（已完成）
2. 🟡 决策开放问题 §17.3 中的 4 项
3. 🔜 W1 Day 1：跑 `tokenknows-web/00-bootstrap.md`（已完成 bootstrap，本周补 MSW + 通用三态组件 + SSE-friendly proxy）
4. 🔜 W2 末（**4 小时**）：搭 `tokenknows-api` 仓库骨架，把 17.1 列出的 8 个复制动作完成。这让 Track B S1 起跑线提前 1 周
5. 🔜 W4 末：评估商业反馈，决定走 Track A 持续打磨还是 Track B 启动
