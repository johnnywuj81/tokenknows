# TokenKnows · AI 研发知识资产引擎

> 把每一次大模型调用,都沉淀为可复用、可审计、可发布的组织知识资产。

[![status](https://img.shields.io/badge/MVP-15%2F15%20屏完成-d97757)](engineering_handoff/README.md)
[![polish](https://img.shields.io/badge/打磨-持久化%20%2B%20SSE%20%2B%20diff%20%2B%20TipTap%20Node-788c5d)](engineering_handoff/demo-walkthrough.md)
[![demo](https://img.shields.io/badge/5%20分钟%20demo-walkthrough.mp4-3d6a96)](engineering_handoff/walkthrough.mp4)
[![data sources](https://img.shields.io/badge/数据源-claude%20%C2%B7%20github%20%C2%B7%20cursor%20%C2%B7%20vscode%20%C2%B7%20local--docs-3d6a96)](scripts/launchd/README.md)
[![CI](https://img.shields.io/badge/CI-self--hosted%20macOS%20ARM64-141413)](.github/workflows/ci.yml)
[![stack](https://img.shields.io/badge/stack-React%2019%20%2B%20FastAPI%20%2B%20Ollama-141413)](engineering_handoff/Architecture.md)

私有化部署的 AI 研发知识资产平台。自动采集 Claude Code / Cursor / VS Code / GitHub 的研发过程,识别架构决策、Bug 复盘、Prompt 模式,生成项目周报 / 技术方案 / ADR / 复盘报告——每段内容都可回溯到原始 PR / 对话/Commit。

**默认零出域**:三层 LLM 出域门禁 + 完整审计 + 客户密钥客户管。

---

## 🎬 5 分钟 Demo

▶ **录屏视频**: [`engineering_handoff/walkthrough.mp4`](engineering_handoff/walkthrough.mp4)(5.6 MB, 5:00, 含中文配音 + 字幕)

> 演示路径: 数据汇聚 → 真 LLM 生成(Ollama minimax-m2)→ 证据链 → 重生成 → 审批 → 脱敏 → 发布 + 版本 diff

12 个关键画面截图(点开看大图):

| 1 工作台 | 2 事件抽屉 | 3 文档列表 | 4 文档结果页 |
|---|---|---|---|
| [![](engineering_handoff/demo-screenshots/01-workbench.png)](engineering_handoff/demo-screenshots/01-workbench.png) | [![](engineering_handoff/demo-screenshots/02-event-drawer.png)](engineering_handoff/demo-screenshots/02-event-drawer.png) | [![](engineering_handoff/demo-screenshots/03-document-list.png)](engineering_handoff/demo-screenshots/03-document-list.png) | [![](engineering_handoff/demo-screenshots/04-document-page.png)](engineering_handoff/demo-screenshots/04-document-page.png) |
| **5 证据链抽屉** | **6 重生成对话框** | **7 审批视图** | **8 脱敏确认** |
| [![](engineering_handoff/demo-screenshots/05-evidence-drawer.png)](engineering_handoff/demo-screenshots/05-evidence-drawer.png) | [![](engineering_handoff/demo-screenshots/06-regenerate-dialog.png)](engineering_handoff/demo-screenshots/06-regenerate-dialog.png) | [![](engineering_handoff/demo-screenshots/07-review-page.png)](engineering_handoff/demo-screenshots/07-review-page.png) | [![](engineering_handoff/demo-screenshots/08-redaction-page.png)](engineering_handoff/demo-screenshots/08-redaction-page.png) |
| **9 发布对话框** | **10 发布回执 + diff** | **11 LLM 出域** | **12 实例管理** |
| [![](engineering_handoff/demo-screenshots/09-publish-dialog.png)](engineering_handoff/demo-screenshots/09-publish-dialog.png) | [![](engineering_handoff/demo-screenshots/10-publish-receipt.png)](engineering_handoff/demo-screenshots/10-publish-receipt.png) | [![](engineering_handoff/demo-screenshots/11-settings-llm.png)](engineering_handoff/demo-screenshots/11-settings-llm.png) | [![](engineering_handoff/demo-screenshots/12-admin.png)](engineering_handoff/demo-screenshots/12-admin.png) |

---

## 🚀 Quick Start · 三步本机起来

```bash
# 1. 启动 Ollama (本地 LLM 推理, 替代云端 OpenAI/Anthropic)
ollama serve &
# 已含 minimax-m2:cloud / gpt-oss:20b 即可, 否则 ollama pull minimax-m2:cloud

# 2. 起后端 (FastAPI + SQLite 持久化, 含 LLM Gateway 三层出域门禁)
cd code/tokenknows-api
cp .env.local.example .env.local 2>/dev/null  # 配置可选, 默认走 ollama
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001

# 3. 起前端 (React 19 + Vite + MSW mock 部分接口)
cd code/tokenknows-web
npm install
npm run dev
# 打开 http://localhost:5173

# (可选) 一键准备演示数据 + 跳转 URL 列表
./engineering_handoff/demo-seed.sh
```

详细演示脚本(每屏 25 秒, 含台词): [`engineering_handoff/demo-walkthrough.md`](engineering_handoff/demo-walkthrough.md)

---

## ✨ 实施完成度 (MVP)

| 类别 | 项 | 状态 |
|---|---|---|
| **15 屏 UI** | T01 鉴权 / T02 项目向导 / T03 工作台 / T04 事件抽屉 / T05 文档列表 / T06 文档页 / T07 证据链 / T08 重生成 / T09 审批 / T10 脱敏 / T11 发布 / T12 回执 / T13 设置 / T14 LLM出域 / T15 Admin | ✅ 15/15 |
| **后端** | FastAPI + LLM Gateway + 5 阶段生成流水线 + SSE | ✅ |
| **真 LLM** | Ollama 第 4 个 provider 接入, minimax-m2:cloud 5-10s/章 | ✅ |
| **持久化** | SQLite 6 表 + cache-aside, kill -9 不掉数据 | ✅ |
| **打磨** | TipTap [N] Node + jsdiff 版本对比 + EventSource SSE | ✅ |
| **Demo** | 5 分钟视频 walkthrough.mp4 (TTS 配音 + 字幕) | ✅ |

详见: [`engineering_handoff/Architecture.md`](engineering_handoff/Architecture.md) · [`engineering_handoff/TaskTechDesign.md`](engineering_handoff/TaskTechDesign.md)

---

## 📁 目录结构

```
TokenKnows/
├── README.md                              ← 你正在看
├── BRD_AI研发知识资产引擎.md              ← 商业需求文档 (v0.2)
├── Pitch_TokenKnows_Pilot.md             ← 试点客户提案
├── PRD_TokenKnows_MVP.md                 ← 产品需求文档 (MVP)
├── TDD_TokenKnows_MVP.md                 ← 技术设计文档 (MVP)
├── DesignHandoff_TokenKnows_MVP.md       ← 设计交付 · 颜色/字体/组件/每屏规格
├── DesignTasks_TokenKnows_MVP.md         ← 设计任务清单
├── assets/                                ← 旅程流程图 / ER 图等 SVG
├── mockups/                               ← 15 个 HTML 像素级 mockup
├── figma_handoff/                         ← Figma 截图 / PNG
├── engineering_handoff/                   ← 工程交付包
│   ├── README.md                          ← 4 周 sprint 计划
│   ├── CLAUDE.md                          ← AI 项目记忆
│   ├── Architecture.md                    ← 宏观架构 + 双轨里程碑 (v0.2)
│   ├── SharedFoundations.md               ← 项目地基 12 节
│   ├── TaskTechDesign.md                  ← 15 任务级技术方案
│   ├── 00-bootstrap.md                    ← 前端初始化命令
│   ├── dev-env-setup.md                   ← 开发环境
│   ├── tailwind.config.ts                 ← Tailwind 配色 token
│   ├── tokens.css                         ← CSS 变量
│   └── tasks/T01–T15.md                   ← 每屏施工任务包
├── code/
│   ├── tokenknows-web/                    ← React 19 + Vite 8 + Tailwind v4 前端
│   └── tokenknows-api/                    ← FastAPI + SQLite + LLM Gateway + 5阶段流水线
├── plugins/                                ← 5 个数据采集器
│   ├── claude-code/sync.py                 ← ~/.claude/projects/*.jsonl 增量
│   ├── github/sync.py                      ← REST API 轮询
│   ├── cursor/sync.py                      ← state.vscdb 只读
│   ├── vscode-tokenknows/                  ← VS Code 扩展 .vsix
│   └── local-docs/sync.py                  ← watchdog .md/.txt
├── scripts/
│   └── launchd/                            ← 4 plist + install/uninstall.sh
└── .github/workflows/ci.yml                ← self-hosted runner 4-job
```

---

## 📡 数据采集 · 5 个插件并发跑

> 全本地, **不需要 ngrok / 公网 webhook tunnel**。崩溃自动重启, 重启系统自动拉起。

| 插件 | 来源 | 触发模式 | trust_score(典型) |
|---|---|---|---|
| **claude-code** | `~/.claude/projects/*.jsonl` | 30s 轮询(增量 offset) | 0.79 (user prompt) / 0.91 (assistant + tool) |
| **github** | GitHub REST API · PR / Issue / Commit | 5min 轮询 | 0.65 (open issue) / 0.95 (merged PR) |
| **cursor** | `Cursor/.../state.vscdb` (只读 SQLite) | 60s 轮询 | 0.80 (assistant 对话) |
| **vscode** | VS Code 扩展 `onDidSaveTextDocument` | buffer + 10s flush | 0.79 (文件保存) |
| **local-docs** | `~/Documents/*.md` `.txt` (watchdog) | 实时 + 2s debounce | 0.77 (≥500 字) |

### 一键安装

```bash
# 4 个 python 插件 → macOS LaunchAgent (崩溃重启 + 系统重启拉起)
./scripts/launchd/install.sh
# 自定义: TOKENKNOWS_BACKEND=... GITHUB_REPO=... LOCAL_DOCS_DIR=... ./install.sh

# 状态/日志/卸载
launchctl list | grep com.tokenknows
tail -f ~/Library/Logs/tokenknows/*.log
./scripts/launchd/uninstall.sh

# VS Code 扩展 (一次性)
code --install-extension plugins/vscode-tokenknows/tokenknows-vscode-0.2.0.vsix
```

详细行为 / 排错 / 多机部署 → [`scripts/launchd/README.md`](./scripts/launchd/README.md)

### trust_score & 证据综合评分

每个插件给 event 计算 trust:
```
trust_score = 0.6 × source_authority + 0.4 × extraction_confidence
```
后端 _stage_evidence 用 cosine × trust × recency 综合排序选 top-4:
```
final = 0.6 × cosine + 0.25 × trust + 0.15 × recency
```
recency 半衰期 30 天 (`exp(-days × ln2 / 30)`)。证据强制跨 ≥2 个 source_type, 避免单一来源。

---

## 🔧 CI · self-hosted runner

GitHub Actions runner 跑在本机 macOS ARM64 (`actions-runner/`), 4 job 并发, 单次 push 约 30s 内绿:

| Job | 内容 | 典型时长 |
|---|---|---|
| `web` | tsc --noEmit + ESLint + vite build | ~25s |
| `api` | ruff check + import smoke + (optional) pytest | ~10s |
| `plugins` | 4 个 python 插件 py_compile + VS Code 扩展 tsc | ~15s |
| `status` | 聚合 3 job 结果, 任一失败则 fail | ~2s |

self-hosted 原因: 早期 ubuntu-latest 计费失败, 也避免上传源码到 GitHub-hosted runner。
Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

---

## 🛠 仅前端跑(快速预览)

```bash
cd code/tokenknows-web
npm install && npm run dev
# 5173 端口, MSW 拦截部分 /api/v1, 真后端 8001 接 LLM 生成
```

fixture 账号: `demo@tokenknows.local` + 任意密码。

---

## 📚 文档导航 (按"问什么先看什么")

| 想了解… | 看这份 |
|---|---|
| 产品做什么 / 为什么 / 商业判断 | [BRD](./BRD_AI研发知识资产引擎.md) + [Pitch](./Pitch_TokenKnows_Pilot.md) |
| 产品验收 / 用户旅程 / NFR | [PRD](./PRD_TokenKnows_MVP.md) |
| 技术架构 / API / Schema / 部署 | [TDD](./TDD_TokenKnows_MVP.md) |
| 颜色 / 字体 / 组件 / 每屏视觉 | [DesignHandoff](./DesignHandoff_TokenKnows_MVP.md) |
| 宏观施工动线 / 双轨里程碑 / 复用源 | [Architecture](./engineering_handoff/Architecture.md) |
| `src/` 文件级地基 / 路由 / token 系统 | [SharedFoundations](./engineering_handoff/SharedFoundations.md) |
| 每屏关键工程决策 / 已知坑补充 | [TaskTechDesign](./engineering_handoff/TaskTechDesign.md) |
| 该屏具体怎么干 (T01-T15) | [engineering_handoff/tasks/](./engineering_handoff/tasks/) |
| 像素级视觉对照 | [mockups/](./mockups/) 浏览器直接打开 |

---

## 🔒 私有化承诺

- 默认零出域 · 三层 LLM 开关(实例 ∧ 项目 ∧ 任务)全 ON 才允许云端调用
- 客户密钥客户管 · TokenKnows 厂商 0 写入、0 读取
- 完整出域审计 · 仅留客户本地, 不上传
- 一键关停 · 紧急情况进入"全离线模式"

详见 [Pitch §5 安全与隐私](./Pitch_TokenKnows_Pilot.md) 与 [PRD §6.7 数据驻留与出域控制](./PRD_TokenKnows_MVP.md)。

---

© 2026 TokenKnows
