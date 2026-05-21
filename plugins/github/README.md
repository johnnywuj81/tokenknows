# TokenKnows · GitHub 插件 v0

两种接入方式 (任选其一或并用):

| 方式 | 速度 | 公网 | 推荐场景 |
|---|---|---|---|
| **API 轮询** (`sync.py`) | 5 分钟级 | 不需要 | 本机演示 / 私有仓 / 不想配 webhook |
| **Webhook** (backend) | 秒级 | 需要 ngrok | 长跑实例 / 生产部署 / 多人协作 |

## 一. API 轮询

### 安装

```bash
pip install requests
```

### Auth

优先 `GH_TOKEN` 环境变量,否则用 `gh auth token`。

```bash
# 用 gh CLI (推荐)
gh auth login
# 或直接 env
export GH_TOKEN=ghp_xxx...
```

### 跑

```bash
# 一次:
python3 plugins/github/sync.py --repo johnnywuj81/tokenknows

# 多 repo:
python3 plugins/github/sync.py \
  --repo johnnywuj81/tokenknows \
  --repo your-org/another-repo

# 持续监听 (5 分钟轮询):
python3 plugins/github/sync.py --repo johnnywuj81/tokenknows --watch
```

### 数据流

```
GitHub REST API /repos/<r>/{pulls,issues,commits}
        ↓ paginate (per_page=100, max 20 页)
   GET ?since=<last_seen_iso>  (issues / commits 支持)
        ↓ map: pr_event / issue_event / commit
   Event { content_hash = sha256(...) }
        ↓ POST /api/v1/projects/:id/events
   backend 去重 → SQLite events 表 → 工作台
```

State 存 `~/.tokenknows/github_state.json`,per-repo 三类水位 (prs / issues / commits)。

### 重置

```bash
python3 plugins/github/sync.py --repo owner/repo --reset
```

---

## 二. Webhook (可选, 生产推荐)

### 步骤

1. **暴露端口**(开发用 ngrok / cloudflared,生产用 nginx):
   ```bash
   ngrok http 8001
   # https://abc123.ngrok-free.app
   ```

2. **设 secret**(本机 backend):
   ```bash
   export GITHUB_WEBHOOK_SECRET=$(openssl rand -hex 32)
   # 重启 uvicorn 让它读到
   ```

3. **GitHub repo 配置**:
   - Repo Settings → Webhooks → Add webhook
   - **Payload URL**: `https://abc123.ngrok-free.app/api/v1/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: 上面生成的 32 字节 hex
   - **Events**: 勾 `Pull requests`, `Issues`, `Pushes`(必要时也勾 Issue comments)

4. **验证**:
   - GitHub 自动发一个 `ping` 事件,端点回 `{"ok":true,"pong":true}`
   - 之后 PR 开/合/重开 + Issue + Push 都秒级流入

### 支持的事件

| GitHub event | action | 入库为 |
|---|---|---|
| `pull_request` | opened / closed / reopened / synchronize / ready_for_review | `pr_event` |
| `issues` | opened / closed / reopened / edited | `issue_event` |
| `push` | (per commit) | `commit` |
| `ping` | — | 200 pong, 不入库 |

### 签名验证

后端用 `GITHUB_WEBHOOK_SECRET` env 校验 `X-Hub-Signature-256`。未配 secret 时接受任何请求(本地开发用)。

---

## 三. 与 Claude Code 插件并用

两者推同一个后端 `/events` 端点,backend 用 `(project_id, content_hash)` 唯一约束去重。即使你同时:

- `python3 plugins/claude-code/sync.py --watch`
- `python3 plugins/github/sync.py --repo owner/repo --watch`
- 还接了 webhook

不会有重复事件。
