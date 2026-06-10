#!/usr/bin/env bash
# TokenKnows 一键本机起 (fresh clone → 可用 UI)
#
# 用法:
#   ./scripts/dev-up.sh                # setup (幂等) + 起后端(后台) + 前端(前台)
#   ./scripts/dev-up.sh --seed         # 同上, 先灌 demo 数据
#   ./scripts/dev-up.sh --setup-only   # 只做依赖安装/env 拷贝, 不启动 (CI/验证用)
#
# 环境变量:
#   API_PORT   后端端口 (默认 8001)
#   WEB_PORT   前端端口 (默认 5173)
#
# Ctrl-C 退出时自动停掉后台 uvicorn.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$REPO_ROOT/code/tokenknows-api"
WEB_DIR="$REPO_ROOT/code/tokenknows-web"
API_PORT="${API_PORT:-8001}"
WEB_PORT="${WEB_PORT:-5173}"

SETUP_ONLY=0
SEED=0
for arg in "$@"; do
  case "$arg" in
    --setup-only) SETUP_ONLY=1 ;;
    --seed)       SEED=1 ;;
    *) echo "unknown arg: $arg (支持 --setup-only / --seed)" >&2; exit 2 ;;
  esac
done

# ─── 前置检查 ─────────────────────────────────────────────
err=0
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)' 2>/dev/null || echo 0)
if [ "$PY_OK" != "1" ]; then echo "✗ 需要 Python ≥ 3.11 (现: $(python3 --version 2>&1))"; err=1; fi
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$NODE_MAJOR" -lt 20 ]; then echo "✗ 需要 Node ≥ 20 (现: $(node --version 2>/dev/null || echo 未装))"; err=1; fi
[ "$err" = "1" ] && exit 1

if command -v ollama >/dev/null 2>&1; then
  echo "✓ Ollama 已装 (本地推理可用, 零云端 key)"
else
  echo "⚠ Ollama 未装 — 想全本地跑 LLM 流水线: https://ollama.com (或在 .env.local 配云端 key)"
fi

# ─── 后端 setup (幂等) ────────────────────────────────────
echo ""
echo "── 后端 setup ($API_DIR)"
cd "$API_DIR"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  echo "  ✓ venv 创建"
fi
if [ ! -x .venv/bin/uvicorn ]; then
  .venv/bin/pip install --quiet -e ".[dev]"
  echo "  ✓ pip install -e \".[dev]\""
else
  echo "  · 依赖已装 (重装: rm -rf code/tokenknows-api/.venv)"
fi
if [ ! -f .env.local ] && [ -f .env.local.example ]; then
  cp .env.local.example .env.local
  echo "  ✓ .env.local 从 example 创建 (默认 Ollama)"
fi

# ─── 前端 setup (幂等) ────────────────────────────────────
echo ""
echo "── 前端 setup ($WEB_DIR)"
cd "$WEB_DIR"
if [ ! -d node_modules ]; then
  npm ci --prefer-offline --no-audit --progress=false
  echo "  ✓ npm ci"
else
  echo "  · node_modules 已存在"
fi
if [ ! -f .env.local ] && [ -f .env.local.example ]; then
  cp .env.local.example .env.local
  # 跟随 API_PORT
  sed -i.bak "s|http://localhost:8001|http://localhost:$API_PORT|" .env.local && rm -f .env.local.bak
  echo "  ✓ .env.local 创建 (API_TARGET → :$API_PORT)"
fi

if [ "$SETUP_ONLY" = "1" ]; then
  echo ""
  echo "✓ setup 完成 (--setup-only, 未启动)"
  exit 0
fi

# ─── 启动 ─────────────────────────────────────────────────
echo ""
echo "── 启动后端 :$API_PORT (后台)"
cd "$API_DIR"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!
trap 'echo ""; echo "── 停后端 (pid $API_PID)"; kill "$API_PID" 2>/dev/null || true' EXIT

# 等 healthz
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$API_PORT/api/v1/healthz" >/dev/null 2>&1; then
    echo "  ✓ 后端就绪"
    break
  fi
  sleep 1
done

if [ "$SEED" = "1" ]; then
  echo "── 灌 demo 数据"
  TOKENKNOWS_API_BASE="http://127.0.0.1:$API_PORT" "$REPO_ROOT/engineering_handoff/demo-seed.sh" || \
    echo "  ⚠ demo-seed 失败 (不阻塞, 可稍后手动跑)"
fi

echo ""
echo "── 启动前端 :$WEB_PORT (前台, Ctrl-C 退出并带停后端)"
echo "   打开 http://localhost:$WEB_PORT"
cd "$WEB_DIR"
exec npm run dev -- --port "$WEB_PORT"
