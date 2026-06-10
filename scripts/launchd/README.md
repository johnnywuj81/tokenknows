# TokenKnows · launchd 单元

> **macOS only** — Linux 用户请直接 `python3 plugins/<x>/sync.py --watch` 手动跑采集器。

把 5 个 Python 插件 (claude-code / codex / github / cursor / local-docs) 装成 macOS LaunchAgent,
后台跑 + 崩溃自动重启 + 系统重启自动拉起。

## 快速上手

```bash
# 1. 装依赖 (一次)
python3 -m pip install requests watchdog

# 2. 装 LaunchAgent (默认本机 demo 设置)
./scripts/launchd/install.sh

# 3. 查看状态
launchctl list | grep com.tokenknows
tail -f ~/Library/Logs/tokenknows/*.log
```

## 自定义配置

```bash
# 自定义后端地址
TOKENKNOWS_BACKEND=http://192.168.1.10:8001 ./install.sh

# 自定义项目 ID
TOKENKNOWS_PROJECT=proj-myteam-001 ./install.sh

# 自定义 GitHub 仓库
GITHUB_REPO=myorg/myrepo ./install.sh

# 自定义本地文档目录
LOCAL_DOCS_DIR=~/Documents/notes ./install.sh

# 组合
TOKENKNOWS_BACKEND=http://10.0.0.5:8001 \
TOKENKNOWS_PROJECT=proj-myteam-001 \
GITHUB_REPO=myorg/myrepo \
LOCAL_DOCS_DIR=~/Documents/projects \
  ./install.sh
```

## 卸载

```bash
./scripts/launchd/uninstall.sh
# 日志保留, 彻底清理:
rm -rf ~/Library/Logs/tokenknows/ ~/.tokenknows/
```

## 安装后产物

| 路径 | 用途 |
|---|---|
| `~/Library/LaunchAgents/com.tokenknows.claude-code.plist` | LaunchAgent 注册 |
| `~/Library/LaunchAgents/com.tokenknows.github.plist` | |
| `~/Library/LaunchAgents/com.tokenknows.cursor.plist` | |
| `~/Library/LaunchAgents/com.tokenknows.local-docs.plist` | |
| `~/Library/Logs/tokenknows/claude-code.log` + `.err.log` | stdout/stderr |
| `~/.tokenknows/sync_state.json` | claude-code 增量 offset |
| `~/.tokenknows/github_sync_state.json` | github last_seen |
| `~/.tokenknows/cursor_sync_state.json` | cursor bubble offset |
| `~/.tokenknows/local_docs_state.json` | local-docs mtime |

## 排错速查

```bash
# 服务是否在跑
launchctl list | grep com.tokenknows
# PID 列 (第 1 列) 是 - 表示没跑 / 数字表示 PID
# Status 列 (第 2 列) 是 0=正常, 其它=最后一次退出码

# 看实时日志
tail -f ~/Library/Logs/tokenknows/claude-code.log
tail -f ~/Library/Logs/tokenknows/claude-code.err.log

# 手动重新加载某个
launchctl unload ~/Library/LaunchAgents/com.tokenknows.claude-code.plist
launchctl load -w ~/Library/LaunchAgents/com.tokenknows.claude-code.plist

# 检查 plist 语法
plutil -lint ~/Library/LaunchAgents/com.tokenknows.claude-code.plist
```

## 行为说明

- **RunAtLoad=true**: 装上立即启动
- **KeepAlive.SuccessfulExit=false**: 非 0 退出码自动重启
- **ThrottleInterval=60/120**: 防止崩溃重启刷屏 (60s 内不再重启)
- **WorkingDirectory=$REPO_ROOT**: 插件相对路径假设从仓库根跑
- **PATH** 包含 `/opt/homebrew/bin` 以兼容 Apple Silicon Homebrew

## 4 个 Agent 的差异

| Agent | 触发频率 | State 文件 | 备注 |
|---|---|---|---|
| claude-code | 30s 轮询 `~/.claude/projects/*.jsonl` | sync_state.json | 增量 line offset |
| github | 5min 轮询 GitHub REST API | github_sync_state.json | 需要 gh auth login 提供 token |
| cursor | 60s 轮询 `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` | cursor_sync_state.json | 只读模式 SQLite, 不阻塞 Cursor 自身 |
| local-docs | watchdog 实时 + 2s debounce | local_docs_state.json | 默认监听 `~/Documents`, 可自定义 |

## 与 docker-compose 后端的关系

如果你用 `docker-compose up` 起后端, 它会绑 `host.docker.internal:8001` →
**本机环境下**仍可走 `http://localhost:8001`,
**Linux 环境**需要把 plist 中 `BACKEND_URL` 替换为 host IP。

---

# 应用服务 LaunchAgent (api + web)

> 上面 4 个是「数据采集插件」(install.sh 管)。下面是「应用本体」两个服务,
> **手写 plist, 不走 install.sh**,因为路径 / 端口是单机特定的。

| Label | 作用 | 端口 | plist 来源 |
|-------|------|------|-----------|
| `com.tokenknows.api` | FastAPI 后端 (uvicorn) | 8001 | 手写 `~/Library/LaunchAgents/com.tokenknows.api.plist` |
| `com.tokenknows.web` | Vite dev server | 5173 | 由 `web.sh` 自动生成 |

## web.sh — 管 Vite LaunchAgent

**为什么单独一个脚本**:launchd 无登录 shell,plist 里 node 必须是绝对路径;
而 nvm 的 node 路径带版本号 (`.../v23.10.0/bin/node`),nvm 一升级旧目录被删,
plist 就失效 (launchd 报 ENOENT,Vite 起不来)。`web.sh` 每次 install/reload
都**自动探测当前 node** 重渲染 plist,把这个脆弱点自动化掉。

```bash
./scripts/launchd/web.sh install     # 首次安装 (探测 node + 渲染 + load)
./scripts/launchd/web.sh reload      # nvm 升级 node 后跑这个 (重探测 + 重渲染 + 重载)
./scripts/launchd/web.sh status      # launchctl 状态 + 端口 + 双栈 HTTP 健康检查
./scripts/launchd/web.sh uninstall   # 卸载 (日志保留)
```

node 探测优先级:`NODE_BIN` env > `command -v node`(用户 nvm use 的版本) >
nvm 目录里最新 mtime 的 node > Homebrew/系统 node。

**关键约定**:web.sh 用 `--host 127.0.0.1` 显式绑 IPv4。Node 18+ 默认把
`localhost` 解析为 IPv6 `[::1]`,Chrome 走 IPv4 path 会 `Connection refused` —
这是「localhost:5173 时通时不通」的根因。`package.json` 的 `dev` 脚本也已带此 flag。

env 覆盖:`TOKENKNOWS_WEB_DIR` / `TOKENKNOWS_WEB_PORT` / `NODE_BIN`。
