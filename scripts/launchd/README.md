# TokenKnows · launchd 单元

把 4 个 Python 插件 (claude-code / github / cursor / local-docs) 装成 macOS LaunchAgent,
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
