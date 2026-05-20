# 开发环境隔离指南

> 适用于 Mac (Apple Silicon / Intel)。
> 解决"我装的东西别污染我电脑、不同项目互不影响、明年还能复现"三件事。

---

## TL;DR · 一图看完

| 你要做的事 | 用什么 | 为什么 |
|---|---|---|
| 前端跑 Node | **nvm + .nvmrc** | 不同项目可能不同 Node 版本 |
| 前端装包 | **npm install**(自动 node_modules) | Node 天然项目级隔离,无需 venv |
| 后端跑 Python | **uv** + `.venv/` | 全局 pip 必爆炸,uv 比 venv 快 100 倍 |
| 跑 Postgres / Redis / MinIO | **Docker Compose** | 别 brew install,Mac 上数据服务用 brew 是慢性自杀 |
| 管理密钥 / 配置 | **`.env` + `.env.example`** | 别把密码 commit 进 git |

时间线:
- **第 1 周(前端)**: 装 nvm + Docker Desktop 就够了
- **第 4 周(开始接后端)**: 装 uv,跑 docker-compose

---

## 1. Node — nvm + .nvmrc

### 装

```bash
# nvm 装到用户目录,不会污染系统 Node
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

# 重启终端,或 source 一下
source ~/.nvm/nvm.sh

# 装 Node 22(本项目用)
nvm install 22
nvm alias default 22

# 验证
node -v   # v22.x.x
which node # /Users/wujun/.nvm/versions/node/v22.x.x/bin/node
```

### 用

在 `tokenknows-web` 仓库根目录:

```bash
echo "22" > .nvmrc
git add .nvmrc
```

之后任何人(包括明年的你)`cd` 进这个目录,跑 `nvm use` 就自动切到 Node 22。

可选自动化(进目录自动切):

```bash
# 加到 ~/.zshrc
cat >> ~/.zshrc << 'EOF'
# nvm 自动切换
autoload -U add-zsh-hook
load-nvmrc() {
  local node_version="$(nvm version)"
  local nvmrc_path="$(nvm_find_nvmrc)"
  if [ -n "$nvmrc_path" ]; then
    local nvmrc_node_version=$(nvm version "$(cat "${nvmrc_path}")")
    [ "$nvmrc_node_version" = "N/A" ] && nvm install
    [ "$nvmrc_node_version" != "$node_version" ] && nvm use
  fi
}
add-zsh-hook chpwd load-nvmrc
load-nvmrc
EOF
source ~/.zshrc
```

### 不要做的事

- ❌ `brew install node` — 装的是系统级,改版本很麻烦
- ❌ 用 npm 装全局包 `-g` 来"管理"工具 — 用 npx 现取现用

---

## 2. Python — uv

`uv` 是 2024 年 Astral 出的新工具,2026 年已经是 Python 圈事实标准。比传统 `python -m venv + pip` 快 100 倍,装包/锁定依赖/虚拟环境一把抓。

### 装

```bash
brew install uv
# 验证
uv --version
```

### 用 — 后端仓库初始化(等你开始建)

```bash
mkdir -p ~/code/tokenknows-api
cd ~/code/tokenknows-api

# 初始化项目(生成 pyproject.toml)
uv init --python 3.11

# 创建 .venv/(项目本地,不会污染系统)
uv venv

# 装包(自动写 pyproject.toml + 锁定 uv.lock)
uv add fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg \
       pydantic pydantic-settings python-multipart python-jose[cryptography] \
       passlib[bcrypt] celery redis boto3 \
       anthropic openai

# 装 dev 依赖
uv add --dev pytest pytest-asyncio httpx ruff mypy

# 跑 FastAPI(自动用 .venv,不用手动 activate)
uv run uvicorn app.main:app --reload --port 8000
```

### 不要做的事

- ❌ 全局 `pip install ...` — 一定会和系统 Python 打架
- ❌ `conda` / `pyenv-virtualenv` — uv 已经覆盖它们所有用例,而且更快
- ❌ requirements.txt 维护 — uv.lock 自动生成,不要手写

### 验证 venv 是否生效

```bash
which python    # 应该是 .venv/bin/python,不是 /usr/bin/python3
python -c "import sys; print(sys.prefix)"  # 应该指向 .venv
```

---

## 3. Postgres / Redis / MinIO — Docker Compose

### 装 Docker Desktop

下载 https://www.docker.com/products/docker-desktop/
开机自动启动可选。Apple Silicon 选 ARM 版。

```bash
# 验证
docker --version
docker compose version
```

### docker-compose.dev.yml(直接用)

放到 `~/code/tokenknows-api/docker-compose.dev.yml`(后端仓库根):

```yaml
# TokenKnows MVP · 本地数据层
# 仅用于开发,生产请参考 TDD §10
#
# 启动: docker compose -f docker-compose.dev.yml up -d
# 停止: docker compose -f docker-compose.dev.yml down
# 清空数据: docker compose -f docker-compose.dev.yml down -v

services:
  postgres:
    image: pgvector/pgvector:pg15
    container_name: tokenknows-postgres
    environment:
      POSTGRES_USER: ${DB_USER:-tokenknows}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-dev_password_change_me}
      POSTGRES_DB: ${DB_NAME:-tokenknows}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-tokenknows}"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: tokenknows-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    container_name: tokenknows-minio
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web 控制台
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3

  # 可选:在浏览器里查 Postgres
  adminer:
    image: adminer:latest
    container_name: tokenknows-adminer
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

### init-db.sql(开启 pgvector + tsvector)

放到 `scripts/init-db.sql`:

```sql
-- pgvector 用于 embedding
CREATE EXTENSION IF NOT EXISTS vector;

-- 中文 / 多语种全文搜索
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- UUID 生成
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### .env.example(版本控制) + .env(本地实际值)

`.env.example`(commit 进 git):

```bash
# Database
DB_USER=tokenknows
DB_PASSWORD=change_me_in_local_env
DB_NAME=tokenknows
DATABASE_URL=postgresql+asyncpg://tokenknows:change_me_in_local_env@localhost:5432/tokenknows

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO (S3 兼容)
MINIO_ENDPOINT=http://localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET=tokenknows-assets

# JWT
JWT_SECRET=generate_with_openssl_rand_hex_32

# LLM Provider (开发阶段任选其一即可)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
LLM_DEFAULT_MODEL=claude-3-5-sonnet-20241022

# App
ENVIRONMENT=development
LOG_LEVEL=DEBUG
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

`.env`(不 commit,真实密码):

```bash
cp .env.example .env
# 改 .env 里的密码,特别是 DB_PASSWORD 和 JWT_SECRET
# 生成 JWT_SECRET: openssl rand -hex 32
```

`.gitignore` 必须包含:

```
.env
.env.local
*.env.*.local
```

### 启动 / 停止 / 重置

```bash
cd ~/code/tokenknows-api

# 启动数据层
docker compose -f docker-compose.dev.yml up -d

# 看日志
docker compose -f docker-compose.dev.yml logs -f

# 看哪些服务在跑
docker compose -f docker-compose.dev.yml ps

# 停止(数据保留)
docker compose -f docker-compose.dev.yml down

# 停止 + 删除所有数据(清空重来)
docker compose -f docker-compose.dev.yml down -v

# 进 Postgres 命令行
docker exec -it tokenknows-postgres psql -U tokenknows
# 进 Redis CLI
docker exec -it tokenknows-redis redis-cli
```

### 验证

| 服务 | 检查方式 |
|---|---|
| Postgres | http://localhost:8080 (adminer) → System: PostgreSQL,Server: postgres,User/DB: tokenknows |
| Redis | `docker exec tokenknows-redis redis-cli ping` → `PONG` |
| MinIO | http://localhost:9001 (用户名/密码: minioadmin / minioadmin) |

### 不要做的事

- ❌ `brew install postgresql` — 用 Homebrew 装 Postgres 是 Mac 开发者一辈子的痛
- ❌ 把 docker volume 删了又删 — 数据没了就没了,重要数据 dump 出来
- ❌ 把 `.env` commit 进 git — 用 `git secret-scan` 之类 pre-commit 检查
- ❌ 生产用 Docker Compose 单机部署 — Compose 只适合 dev 和 demo

---

## 4. 整体目录约定

建议在 `~/code/` 下并列两个仓库:

```
~/code/
├── tokenknows-web/         ← 前端(React 19 + Vite)
│   ├── .nvmrc              ← Node 22
│   ├── node_modules/       ← 自动隔离
│   └── docs/ → symlink     ← 链到 ~/TokenKnows 下的文档
│
└── tokenknows-api/         ← 后端(FastAPI + Python)
    ├── .python-version     ← uv 自动用
    ├── .venv/              ← uv 自动建
    ├── pyproject.toml
    ├── uv.lock
    ├── docker-compose.dev.yml
    ├── .env                ← 不入 git
    ├── .env.example        ← 入 git
    └── scripts/init-db.sql
```

文档库 `~/TokenKnows/` 单独存放,不放在任何仓库里 — 它是源头,两个仓库都通过 symlink 引用。

---

## 5. 备份 / 重装机器时怎么办

一台新 Mac 从零起步,30 分钟搞定:

```bash
# 1. Homebrew(2 分钟)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 基础工具(3 分钟)
brew install git uv docker
brew install --cask docker  # Docker Desktop

# 3. nvm(2 分钟)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.nvm/nvm.sh

# 4. 拉两个仓库 + 文档库(5 分钟)
mkdir -p ~/code
git clone <git url> ~/code/tokenknows-web
git clone <git url> ~/code/tokenknows-api
git clone <git url> ~/TokenKnows  # 或者 dropbox/icloud 同步

# 5. 前端跑起来(5 分钟)
cd ~/code/tokenknows-web
nvm install   # 自动读 .nvmrc
npm install
npm run dev

# 6. 后端跑起来(10 分钟)
cd ~/code/tokenknows-api
cp .env.example .env
# 改 .env 里的密码
docker compose -f docker-compose.dev.yml up -d
uv sync               # 自动建 .venv + 装包,读 uv.lock
uv run alembic upgrade head    # 跑 db migration(如果有)
uv run uvicorn app.main:app --reload
```

无 brew install postgres,无系统 Python pip install,无 node 全局污染 — 全部项目级隔离,卸载 Docker Desktop 即可清空所有数据库相关副作用。

---

## 6. 常见疑问

**Q: 为什么不直接全部用 Docker(包括前端 + 后端的 Python)?**
A: Mac 上 Docker 的 volume mount 性能差(虚拟化层),HMR 会肉眼可见地慢。Native Node + Native Python + Docker 只管数据层,是 2026 年 Mac 开发的最优解。Linux 上无所谓,全 Docker 也快。

**Q: pyenv 还是 uv?**
A: 现在统一用 uv。uv 自带 Python 版本管理(`uv python install 3.11`),pyenv 已经没必要了。

**Q: 后端到底什么时候开始?**
A: 见 README 第 4 周 Day 16。前 3 周前端全 MSW mock,不需要后端跑起来。

**Q: 团队进来新人怎么办?**
A: 把本文档发他;在两个仓库根加一个 `make setup` Makefile 跑完上面所有步骤;15 分钟新人就能 commit 代码。
