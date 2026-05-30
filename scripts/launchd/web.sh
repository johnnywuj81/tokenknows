#!/usr/bin/env bash
# 管理 com.tokenknows.web LaunchAgent (Vite dev server · 自启 + 崩溃自重启).
#
# 为什么单独一个脚本:
#   plist 里 node 路径必须是绝对路径 (launchd 无登录 shell, 不 source nvm),
#   而 nvm 的 node 路径带版本号 (.../v23.10.0/bin/node). nvm 一升级旧版本目录
#   可能被删, plist 就失效 (launchd 报 ENOENT, Vite 起不来). 本脚本每次
#   install/reload 都【自动探测当前 node】重新渲染 plist, 把这个脆弱点自动化掉.
#
# 用法:
#   ./web.sh install     # 探测 node + 渲染 plist + load (首次安装)
#   ./web.sh reload      # 重新探测 node + 重渲染 + unload→load (nvm 升级后跑这个)
#   ./web.sh uninstall   # unload + 删 plist (日志保留供排查)
#   ./web.sh status      # launchctl 状态 + 端口 + 双栈健康检查
#
# 可用 env 覆盖:
#   TOKENKNOWS_WEB_DIR=...   # 默认 <repo>/code/tokenknows-web
#   TOKENKNOWS_WEB_PORT=...  # 默认 5173
#   NODE_BIN=/abs/path/node  # 跳过自动探测, 指定 node

set -euo pipefail

# ─── 配置 ─────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.tokenknows.web"
WEB_DIR="${TOKENKNOWS_WEB_DIR:-$REPO_ROOT/code/tokenknows-web}"
PORT="${TOKENKNOWS_WEB_PORT:-5173}"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/tokenknows"
PLIST="$LAUNCH_DIR/$LABEL.plist"

# ─── node 探测 (本脚本的核心价值) ──────────────────────────
# 优先级:
#   1. NODE_BIN env (手动指定, 一锤定音)
#   2. command -v node (用户交互 shell 里 nvm use 的版本 — 最贴合意图)
#   3. nvm 目录里【最新 mtime】的 node (fallback, 非登录环境也能找到)
detect_node() {
    if [ -n "${NODE_BIN:-}" ]; then
        echo "$NODE_BIN"; return 0
    fi
    if command -v node >/dev/null 2>&1; then
        command -v node; return 0
    fi
    local newest
    newest="$(ls -dt "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | head -1 || true)"
    if [ -n "$newest" ]; then
        echo "$newest"; return 0
    fi
    # Homebrew / 系统 node 兜底
    for cand in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
        [ -x "$cand" ] && { echo "$cand"; return 0; }
    done
    return 1
}

# ─── 渲染 plist (heredoc, 自包含, 不依赖外部模板) ──────────
render_plist() {
    local node_bin="$1"
    local node_dir; node_dir="$(dirname "$node_bin")"
    local vite_js="$WEB_DIR/node_modules/vite/bin/vite.js"

    [ -x "$node_bin" ]   || { echo "✗ node 不可执行: $node_bin" >&2; return 1; }
    [ -f "$vite_js" ]    || { echo "✗ vite.js 缺失 (先 npm install?): $vite_js" >&2; return 1; }
    [ -d "$WEB_DIR" ]    || { echo "✗ web 目录不存在: $WEB_DIR" >&2; return 1; }

    mkdir -p "$LAUNCH_DIR" "$LOG_DIR"
    cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <!-- 由 scripts/launchd/web.sh 自动生成 · 勿手改 (node 路径会随 nvm 升级失效, 跑 web.sh reload 重生成) -->
    <key>ProgramArguments</key>
    <array>
        <string>$node_bin</string>
        <string>$vite_js</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$WEB_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>60</integer>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/web.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/web.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <!-- nvm node bin 放最前, 让 vite spawn 的子进程 (esbuild 等) 找到同版本 node -->
        <key>PATH</key>
        <string>$node_dir:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST_EOF

    # 校验 XML 合法 (坏 plist 会让 launchctl 静默失败)
    if command -v plutil >/dev/null 2>&1; then
        plutil -lint "$PLIST" >/dev/null || { echo "✗ 生成的 plist XML 非法" >&2; return 1; }
    fi
    echo "  ✓ 渲染 plist · node=$node_bin"
}

wait_ready() {
    echo -n "  等 Vite 监听 :$PORT "
    for _ in $(seq 1 40); do
        if curl -s --max-time 2 "http://127.0.0.1:$PORT/" 2>/dev/null | grep -q "<title>"; then
            echo "✓"; return 0
        fi
        echo -n "."; sleep 1
    done
    echo " ✗ (超时 · 看 $LOG_DIR/web.err.log)"; return 1
}

cmd_install() {
    local node_bin; node_bin="$(detect_node)" || { echo "✗ 找不到 node (装 nvm/node 或设 NODE_BIN=...)" >&2; exit 1; }
    render_plist "$node_bin"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load -w "$PLIST"
    echo "  ✓ loaded $LABEL"
    wait_ready || true
    cmd_status
}

cmd_reload() { cmd_install; }   # install 本身幂等 (先 unload 再 load), reload 即重跑

cmd_uninstall() {
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        rm "$PLIST"
        echo "  ✓ removed $LABEL (日志保留在 $LOG_DIR/)"
    else
        echo "  · 未安装: $LABEL"
    fi
}

cmd_status() {
    echo "─── $LABEL 状态 ───"
    local line; line="$(launchctl list 2>/dev/null | grep "$LABEL" || true)"
    if [ -n "$line" ]; then
        echo "  launchctl: $line  (第一列=PID, '-'=没在跑)"
    else
        echo "  launchctl: 未加载"
    fi
    echo -n "  :$PORT 监听: "
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1" pid="$2" "$8}' || echo "(无)"
    printf "  127.0.0.1: "; curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null || echo "不通"
    printf "  localhost: "; curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 3 "http://localhost:$PORT/" 2>/dev/null || echo "不通"
}

# ─── 入口 ─────────────────────────────────────────────────
case "${1:-}" in
    install)   cmd_install ;;
    reload)    cmd_reload ;;
    uninstall) cmd_uninstall ;;
    status)    cmd_status ;;
    *)
        echo "用法: $0 {install|reload|uninstall|status}" >&2
        echo "  install   - 探测 node + 渲染 plist + 加载" >&2
        echo "  reload    - 重新探测 node + 重渲染 + 重载 (nvm 升级后用)" >&2
        echo "  uninstall - 卸载 (日志保留)" >&2
        echo "  status    - 状态 + 双栈健康检查" >&2
        exit 2
        ;;
esac
