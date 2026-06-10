# TokenKnows API

> FastAPI 后端 + LLM Gateway (三层出域门禁 + LiteLLM 多家适配 + 出域审计)
>
> 架构依据: [`engineering_handoff/Architecture.md`](../../engineering_handoff/Architecture.md) §17.1 + §5 (LLM Gateway 详细设计) + [`TDD`](../../docs/product/TDD_TokenKnows_MVP.md) §6.6 / §7

---

## 快速启动 (本地开发)

```bash
cd code/tokenknows-api

# 1. 准备 keys (.env.local 已在 .gitignore 内)
cp .env.example .env.local
# 编辑 .env.local 填入真实 key

# 2. 安装依赖
pip install -e ".[dev]"   # 或 uv pip install -e ".[dev]"

# 3. 启动 (开发模式, 自动 reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 健康检查
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz   # 检查 LLM provider 可达
```

OpenAPI docs: <http://localhost:8000/docs>

---

## 接入的 LLM 厂商 (LiteLLM 包装)

| Provider | 用途 | 默认模型 | 价格 (in/out per 1M tokens) |
|---|---|---|---|
| Anthropic | 主力文档生成 (T06/T08) | claude-sonnet-4-6 | $3 / $15 |
| OpenAI | 备用 + Embedding | gpt-4o / text-embedding-3-small | $2.5 / $10 + $0.02 |
| MiniMax | 价值识别 + 脱敏 LLM 层 (轻量) | abab6.5s-chat | ~¥0.01 |

切换由 `.env.local` 内 `TASK_<X>_PROVIDER` 配置决定; T08 重生成可在 UI 临时切换。

---

## 架构铁律

1. **业务代码不允许直接 `import anthropic/openai`** — 必须走 `app.llm_gateway`。CI 强制 (pyproject.toml [tool.ruff.lint.flake8-tidy-imports])
2. **三层出域门禁** (instance ∧ project ∧ task) 全 ON 才允许 cloud 调用; 任一 OFF 自动降级 / 拒绝
3. **cloud 调用强制写 egress_log** (含 hash_of_request + size + latency + cost_estimate)
4. **CircuitBreaker 包 LLM 调用** (复用 digital_enterprise/core/resilience.py); provider 失败自动 fallback 链

---

## 目录结构

```
tokenknows-api/
├── pyproject.toml
├── .env.example / .env.local (不入 git)
├── Dockerfile
├── app/
│   ├── main.py                       # FastAPI lifespan + 路由挂载
│   ├── config/
│   │   ├── settings.py               # pydantic-settings (读 .env.local)
│   │   └── logging.py                # structlog JSON
│   ├── core/                         # 基础设施 (大部分复用 digital_enterprise)
│   │   ├── resilience.py             # CircuitBreaker + retry_with_backoff (DE 0 修改)
│   │   ├── observability.py          # OpenTelemetry + Prometheus
│   │   └── rate_limiter.py           # Redis 滑动窗口 (DE 移植)
│   ├── llm_gateway/                  # ★ 核心
│   │   ├── interface.py              # LLMTask / LLMMessage / LLMResponse 协议
│   │   ├── router.py                 # 适配器选择 + 三层出域门禁
│   │   ├── audit.py                  # egress_log SQLite 写入
│   │   ├── litellm_client.py         # LiteLLM 统一包装 (replaces 4 个 adapter 文件)
│   │   └── exceptions.py             # EgressDeniedError 等
│   ├── gateway/                      # FastAPI 路由
│   │   └── http_api/
│   │       ├── health.py             # /healthz /readyz
│   │       ├── generation.py         # POST /api/v1/projects/:id/assets/generate
│   │       └── llm_preview.py        # POST /api/v1/llm/egress/preview (T14 dry-run)
│   └── schemas/                      # Pydantic 请求/响应
│       └── generation.py
└── data/
    └── egress.sqlite                 # 出域审计本地存储 (生产换 Postgres)
```

---

## MVP vs Production 差异

| 项 | MVP (当前) | Production (后续) |
|---|---|---|
| egress_log 存储 | SQLite 文件 (`data/egress.sqlite`) | Postgres `egress_log` 表 + 分区 |
| 项目/任务 egress 开关 | 读 `.env.local` 默认值 | DB `projects.task_egress_config` |
| 鉴权 | 暂不强制 (本地 demo) | JWT RS256 + middleware |
| 文档生成 5 阶段持久化 | 内存 + 直接响应 | Celery 任务 + SSE 进度 + DB Asset/Chapter/Evidence |

---

## 与前端 (tokenknows-web) 联调

前端 Vite dev server (5173) 已配 proxy `/api → :8000`。后端启动后:

1. 前端 `mocks/handlers/assets.ts` 的 generate handler 删除 (让 MSW 不拦截 /api/v1/assets/generate)
2. 前端真实调到这里的 `POST /api/v1/projects/:id/assets/generate`
3. 服务返回 Asset(status=generating); 前端 polling 5s 拿 status=draft 后渲染

详见 [Architecture.md §15.3 Track A → Track B 衔接](../../engineering_handoff/Architecture.md)。
