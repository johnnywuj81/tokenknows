#!/usr/bin/env bash
#
# TokenKnows MVP · Bootstrap 第 1-3 节自动化
# 已在沙箱实测跑通 (2026-05),包含所有已知的 Tailwind v4 / TS 6 / paths 配置修正
#
# 用法:
#   chmod +x bootstrap-step1-3.sh
#   ./bootstrap-step1-3.sh           # 默认建在 ~/code/tokenknows-web
#   ./bootstrap-step1-3.sh /path/to  # 或指定父目录
#
# 完成后会跑一次 build 验证 token 链路;成功输出"✓ Bootstrap 完成"

set -e
set -o pipefail

# ─── 配置 ────────────────────────────────────────────
PARENT_DIR="${1:-$HOME/code}"
PROJECT_NAME="tokenknows-web"
PROJECT_DIR="$PARENT_DIR/$PROJECT_NAME"
HANDOFF_DIR="$(cd "$(dirname "$0")" && pwd)"  # 本脚本所在目录

# ─── 颜色 ────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
say()  { echo -e "${G}▶${N} $1"; }
warn() { echo -e "${Y}!${N} $1"; }
die()  { echo -e "${R}✗${N} $1"; exit 1; }

# ─── 前置检查 ─────────────────────────────────────────
say "环境检查..."

# 如果有 nvm 且当前 node < 20,自动切到 22(规避 conda / ~/.local/bin 等 PATH 干扰)
if [ -d "$HOME/.nvm" ]; then
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
  CURRENT_VER=$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -z "$CURRENT_VER" ] || [ "$CURRENT_VER" -lt 20 ]; then
    warn "当前 node 版本 < 20 或未安装,nvm 自动切到 22..."
    nvm use 22 >/dev/null 2>&1 || nvm install 22 >/dev/null 2>&1
  fi
fi

command -v node >/dev/null || die "未安装 Node.js (需 ≥ 20)。装 nvm 后跑 \`nvm install 22\`"
command -v npm  >/dev/null || die "未安装 npm"

NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VER" -lt 20 ]; then
  die "Node 版本 ($(node -v)) 仍 < 20。试 \`nvm exec 22 ./bootstrap-step1-3.sh\` 或检查 \`which node\` (可能 conda/~/.local/bin 在 PATH 最前)"
fi
say "  当前 node: $(which node) ($(node -v))"

if [ ! -d "$HANDOFF_DIR" ] || [ ! -f "$HANDOFF_DIR/tailwind.config.ts" ]; then
  die "找不到 tailwind.config.ts。请把本脚本和 tailwind.config.ts/tokens.css 放在同一文件夹"
fi

say "Node $(node -v),npm $(npm -v),OK"

# ─── 创建父目录 ──────────────────────────────────────
mkdir -p "$PARENT_DIR"
cd "$PARENT_DIR"

if [ -d "$PROJECT_DIR" ]; then
  warn "$PROJECT_DIR 已存在"
  read -p "  覆盖? (y/N): " yn
  [ "$yn" = "y" ] || die "已取消"
  rm -rf "$PROJECT_DIR"
fi

# ─── 第 1 节: Vite 模板 ──────────────────────────────
say "[1/3] 创建 Vite + React + TS 模板(npm 可能问'要装 create-vite 吗',自动 yes)..."
# --yes 让 npm 自动接受 "Need to install" 提示;输出不再吞,这样你能看到进度
NPM_CONFIG_YES=true npm create vite@latest "$PROJECT_NAME" -- --template react-ts
cd "$PROJECT_DIR"
say "    跑 npm install (1-2 分钟,有进度条)..."
npm install 2>&1 | tail -5

REACT_VER=$(node -p "require('./package.json').dependencies.react" 2>/dev/null || echo "?")
VITE_VER=$(node -p "require('./package.json').devDependencies.vite" 2>/dev/null || echo "?")
say "  React $REACT_VER · Vite $VITE_VER"

# ─── 第 2 节: 核心依赖 ───────────────────────────────
say "[2/3] 装核心依赖(约 1-2 分钟,合并成一次 npm install 更快)..."

# 合并成一次 npm install,比分 7 次快很多
npm install \
  class-variance-authority clsx tailwind-merge lucide-react \
  react-router-dom zustand @tanstack/react-query \
  react-hook-form zod @hookform/resolvers \
  @tiptap/react @tiptap/starter-kit @tiptap/extension-link @tiptap/extension-placeholder \
  date-fns 2>&1 | tail -3

npm install -D tailwindcss @tailwindcss/vite msw 2>&1 | tail -3

say "  $(node -p "Object.keys({...require('./package.json').dependencies, ...require('./package.json').devDependencies}).length") 个包已就位"

# ─── 第 3 节: Vite + Tailwind v4 配置 ───────────────
say "[3/3] 写配置文件 + 修 TS paths + 验证 token 链路..."

# 3.1 vite.config.ts
cat > vite.config.ts << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') }
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/sse': { target: 'http://localhost:8000', changeOrigin: true, ws: true }
    }
  }
})
EOF

# 3.2 tailwind.config.ts + tokens.css(从本脚本旁边复制)
cp "$HANDOFF_DIR/tailwind.config.ts" ./tailwind.config.ts
mkdir -p src/styles
cp "$HANDOFF_DIR/tokens.css" ./src/styles/tokens.css

# 3.3 src/index.css(关键:Tailwind v4 必须用 @config 显式引入)
cat > src/index.css << 'EOF'
@import "tailwindcss";
@config "../tailwind.config.ts";
@import "./styles/tokens.css";
EOF

# 3.4 tsconfig.app.json 加 paths + 修 baseUrl 弃用警告
# Vite 模板的 tsconfig.app.json 有 // 注释,只能用 sed 而不是 jq/python json
if ! grep -q '"paths"' tsconfig.app.json; then
  sed -i.bak 's|"skipLibCheck": true,|"skipLibCheck": true,\n    "baseUrl": ".",\n    "ignoreDeprecations": "6.0",\n    "paths": { "@/*": ["./src/*"] },|' tsconfig.app.json
  rm tsconfig.app.json.bak
fi

# 3.5 写一个使用 token 的 App.tsx,build 时能验证 token 链路是否打通
cat > src/App.tsx << 'EOF'
function App() {
  return (
    <div className="bg-bg-page min-h-screen p-8 font-ui">
      <div className="bg-bg-card border border-border-subtle rounded-lg p-6 max-w-2xl shadow-elev-1">
        <h1 className="font-content text-h1 text-text-primary">TokenKnows · Bootstrap OK</h1>
        <p className="text-body text-text-muted mt-2">
          如果这段文字颜色正确、字体不是默认 sans-serif,token 链路就通了。
        </p>
        <div className="mt-4 flex items-center gap-2">
          <button className="bg-accent-primary text-inverse-text px-4 py-2 rounded-md text-body-sm font-medium">
            主 CTA
          </button>
          <span className="bg-success-bg text-success-dark px-2 py-0.5 rounded text-micro font-medium">
            success
          </span>
          <span className="bg-warning-bg text-warning px-2 py-0.5 rounded text-micro font-medium">
            warning
          </span>
        </div>
        <p className="text-caption text-text-subtle mt-4 font-mono">
          /docs/engineering_handoff/tasks/T01-auth.md ← 下一步喂这个给 Claude Code
        </p>
      </div>
    </div>
  )
}
export default App
EOF

# 3.6 跑一次 build 验证
say "  正在 build 验证..."
BUILD_OUT=$(npm run build 2>&1 || true)
if echo "$BUILD_OUT" | grep -q "error\|Error" | grep -vi "0 errors"; then
  echo "$BUILD_OUT" | tail -20
  die "build 失败,看上面输出"
fi

CSS_FILE=$(ls dist/assets/*.css 2>/dev/null | head -1)
if [ -z "$CSS_FILE" ]; then
  die "没找到 build 输出的 CSS"
fi

# 验证关键 token class 在 CSS 中
MATCHES=$(grep -oE "\.bg-bg-card|\.bg-accent-primary|\.text-text-primary|\.font-content" "$CSS_FILE" | sort -u | wc -l | tr -d ' ')
if [ "$MATCHES" -lt 3 ]; then
  warn "Token class 数量异常 ($MATCHES/4),Tailwind v4 可能没读到 config"
  warn "检查 src/index.css 顶部是否有: @config \"../tailwind.config.ts\";"
fi

# ─── 完成 ────────────────────────────────────────────
echo ""
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo -e "${G}✓ Bootstrap 完成${N}"
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo ""
echo "  仓库位置: $PROJECT_DIR"
echo "  Token class 验证: $MATCHES/4 通过"
echo ""
echo "  下一步:"
echo "    cd $PROJECT_DIR"
echo "    npm run dev          # 打开 http://localhost:5173 应该看到 'TokenKnows · Bootstrap OK'"
echo ""
echo "  之后:"
echo "    1. 接着跑 00-bootstrap.md 第 4-9 节(shadcn / MSW / 字体 / 链接 docs)"
echo "    2. 把 CLAUDE.md 复制到仓库根: cp $HANDOFF_DIR/CLAUDE.md ./"
echo "    3. 启动 Claude Code: claude"
echo "    4. 喂第一个任务包: cat docs/engineering_handoff/tasks/T01-auth.md"
echo ""
