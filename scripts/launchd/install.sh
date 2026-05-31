#!/usr/bin/env bash
# 安装 4 个 TokenKnows 插件为 macOS LaunchAgent (后台跑 + 崩溃自动重启).
#
# 用法:
#   ./scripts/launchd/install.sh                            # 默认设置 (本机演示)
#   TOKENKNOWS_BACKEND=http://...  ./install.sh             # 自定义后端
#   GITHUB_REPO=org/repo  ./install.sh                      # 自定义 GitHub 仓库
#   LOCAL_DOCS_DIR=~/Documents/notes  ./install.sh          # 自定义本地文档目录
#
# 卸载: ./scripts/launchd/uninstall.sh

set -euo pipefail

# ─── 配置 (env 可覆盖) ────────────────────────────────────
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$(which python3)}"
BACKEND_URL="${TOKENKNOWS_BACKEND:-http://127.0.0.1:8002}"
PROJECT_ID="${TOKENKNOWS_PROJECT:-proj-demo-001}"
GITHUB_REPO="${GITHUB_REPO:-johnnywuj81/tokenknows}"
LOCAL_DOCS_DIR="${LOCAL_DOCS_DIR:-$HOME/Documents}"

LOG_DIR="$HOME/Library/Logs/tokenknows"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
TEMPLATE_DIR="$REPO_ROOT/scripts/launchd"

# ─── 输入校验 (T144) ────────────────────────────────────────
# 防止 BACKEND_URL / PROJECT_ID / GITHUB_REPO 含 sed 分隔符 '|' 或者其它
# XML-unsafe 字符 (& < >) 导致替换破坏 plist XML 结构, 进而注入额外的
# launchd EnvironmentVariables. 在 single-user dev 场景威胁低, 但 install.sh
# 也可能在 CI / 其他用户机器跑, 校验是廉价的防御.
[[ "$BACKEND_URL"    =~ ^https?://[A-Za-z0-9._:/-]+$ ]] || {
    echo "✗ BACKEND_URL 格式非法 (允许: http(s)://hostname[:port][/path]): $BACKEND_URL" >&2
    exit 1
}
[[ "$PROJECT_ID"     =~ ^[A-Za-z0-9_-]+$ ]] || {
    echo "✗ PROJECT_ID 格式非法 (允许 [A-Za-z0-9_-]): $PROJECT_ID" >&2
    exit 1
}
[[ "$GITHUB_REPO"    =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
    echo "✗ GITHUB_REPO 格式非法 (期望 owner/repo): $GITHUB_REPO" >&2
    exit 1
}
# LOCAL_DOCS_DIR / LOG_DIR / REPO_ROOT 是路径, 不接受 '|' 这类特殊字符
for var_name in LOCAL_DOCS_DIR LOG_DIR REPO_ROOT PYTHON_BIN; do
    val="${!var_name}"
    if [[ "$val" == *"|"* || "$val" == *"<"* || "$val" == *">"* || "$val" == *"&"* ]]; then
        echo "✗ $var_name 含 sed/XML-unsafe 字符 (| < > &): $val" >&2
        exit 1
    fi
done

# ─── 预检 ─────────────────────────────────────────────────
echo "─── TokenKnows LaunchAgent 安装 ───"
echo "  REPO_ROOT       = $REPO_ROOT"
echo "  PYTHON_BIN      = $PYTHON_BIN"
echo "  BACKEND_URL     = $BACKEND_URL"
echo "  PROJECT_ID      = $PROJECT_ID"
echo "  GITHUB_REPO     = $GITHUB_REPO"
echo "  LOCAL_DOCS_DIR  = $LOCAL_DOCS_DIR"
echo "  LOG_DIR         = $LOG_DIR"
echo ""

# 检查 python
if [ ! -x "$PYTHON_BIN" ]; then
    echo "✗ python3 未找到: $PYTHON_BIN" >&2
    exit 1
fi

# 检查必需依赖
"$PYTHON_BIN" -c "import requests, watchdog" 2>/dev/null || {
    echo "✗ python3 缺少 requests / watchdog 包, 请运行:"
    echo "  $PYTHON_BIN -m pip install requests watchdog"
    exit 1
}

# 检查可选依赖 (pdfplumber: local-docs 的 PDF 支持)
if ! "$PYTHON_BIN" -c "import pdfplumber" 2>/dev/null; then
    echo "  ⚠ pdfplumber 未装 — local-docs 将不能处理 .pdf (仅 .md/.txt 可用)"
    echo "    如需 PDF 支持: $PYTHON_BIN -m pip install pdfplumber"
fi

# 检查脚本存在
for f in plugins/claude-code/sync.py plugins/github/sync.py \
         plugins/cursor/sync.py plugins/local-docs/sync.py \
         plugins/codex/sync.py; do
    if [ ! -f "$REPO_ROOT/$f" ]; then
        echo "✗ 缺少: $REPO_ROOT/$f" >&2
        exit 1
    fi
done

# 检查后端可达 (可选 · 不阻断)
if curl -sfo /dev/null "$BACKEND_URL/api/v1/healthz"; then
    echo "  ✓ backend reachable"
else
    echo "  ⚠ backend not reachable now — 装上没事, launchd 会自动重启"
fi
echo ""

# ─── 装文件 ───────────────────────────────────────────────
mkdir -p "$LOG_DIR"
mkdir -p "$LAUNCH_DIR"

for label in claude-code github cursor local-docs codex; do
    src="$TEMPLATE_DIR/com.tokenknows.$label.plist"
    dst="$LAUNCH_DIR/com.tokenknows.$label.plist"
    if [ ! -f "$src" ]; then
        echo "✗ 模板缺失: $src" >&2
        continue
    fi
    # 用 sed 替换占位
    sed \
        -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
        -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
        -e "s|__BACKEND_URL__|$BACKEND_URL|g" \
        -e "s|__PROJECT_ID__|$PROJECT_ID|g" \
        -e "s|__GITHUB_REPO__|$GITHUB_REPO|g" \
        -e "s|__LOCAL_DOCS_DIR__|$LOCAL_DOCS_DIR|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" \
        "$src" > "$dst"

    # bootstrap 之前先 unload (idempotent: 不会失败)
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load -w "$dst"
    echo "  ✓ loaded com.tokenknows.$label"
done

echo ""
echo "─── 安装完成 ───"
echo "查看状态: launchctl list | grep com.tokenknows"
echo "查看日志: tail -f $LOG_DIR/*.log"
echo "卸载:     $REPO_ROOT/scripts/launchd/uninstall.sh"
