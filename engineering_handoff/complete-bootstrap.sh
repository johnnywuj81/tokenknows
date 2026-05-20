#!/usr/bin/env bash
# 接着干完 bootstrap [2/3] 和 [3/3] —— 在已经建好的 tokenknows-web 上补依赖、配置、App.tsx,然后 build 验证。
# 适用于:npm create vite 自动启了 dev server 把脚本卡住的情况。

set -e
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
say() { echo -e "${G}▶${N} $1"; }
die() { echo -e "${R}✗${N} $1"; exit 1; }

PROJECT_DIR="$HOME/TokenKnows/code/tokenknows-web"
HANDOFF_DIR="$(cd "$(dirname "$0")" && pwd)"

[ -d "$PROJECT_DIR" ] || die "找不到 $PROJECT_DIR,先跑 bootstrap-step1-3.sh"
[ -f "$HANDOFF_DIR/tailwind.config.ts" ] || die "找不到 $HANDOFF_DIR/tailwind.config.ts"

# 加载 nvm
if [ -d "$HOME/.nvm" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || true
fi

cd "$PROJECT_DIR"
say "当前 node: $(which node) $(node -v)"

# ─── 清理: 关掉 5173/5174 上还在跑的 vite ─────────────
say "关掉 5173/5174 上残留的 vite dev server..."
for port in 5173 5174 5175; do
  pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    echo "   端口 $port 已释放"
  fi
done

# ─── 第 2 节: 装剩下的依赖 ───────────────────────────
say "[2/3] 装核心依赖 (跑 1 次大 npm install,2-3 分钟)..."
npm install \
  class-variance-authority clsx tailwind-merge lucide-react \
  react-router-dom zustand @tanstack/react-query \
  react-hook-form zod @hookform/resolvers \
  @tiptap/react @tiptap/starter-kit @tiptap/extension-link @tiptap/extension-placeholder \
  date-fns 2>&1 | tail -5

say "    再装 dev 依赖..."
npm install -D tailwindcss @tailwindcss/vite msw 2>&1 | tail -3

DEP_COUNT=$(node -p "Object.keys({...require('./package.json').dependencies, ...require('./package.json').devDependencies}).length")
say "    依赖总数: $DEP_COUNT 个"

# ─── 第 3 节: 配置 ────────────────────────────────────
say "[3/3] 写配置 + token 文件 + App.tsx..."

# 3.1 vite.config.ts (覆盖)
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
echo "   ✓ vite.config.ts"

# 3.2 tailwind.config.ts + tokens.css
cp "$HANDOFF_DIR/tailwind.config.ts" ./tailwind.config.ts
mkdir -p src/styles
cp "$HANDOFF_DIR/tokens.css" ./src/styles/tokens.css
echo "   ✓ tailwind.config.ts + src/styles/tokens.css"

# 3.3 src/index.css 覆盖 (Tailwind v4 关键: @config 指令)
cat > src/index.css << 'EOF'
@import "tailwindcss";
@config "../tailwind.config.ts";
@import "./styles/tokens.css";
EOF
echo "   ✓ src/index.css (含 @config)"

# 3.4 tsconfig.app.json 加 paths
if ! grep -q '"paths"' tsconfig.app.json; then
  sed -i.bak 's|"skipLibCheck": true,|"skipLibCheck": true,\n    "baseUrl": ".",\n    "ignoreDeprecations": "6.0",\n    "paths": { "@/*": ["./src/*"] },|' tsconfig.app.json
  rm tsconfig.app.json.bak
  echo "   ✓ tsconfig.app.json (paths + ignoreDeprecations)"
else
  echo "   - tsconfig.app.json 已有 paths,跳过"
fi

# 3.5 删除 vite 模板默认垃圾
rm -f src/App.css
rm -f src/assets/react.svg
echo "   ✓ 清理默认 App.css / react.svg"

# 3.6 写 token 验证用的 App.tsx
cat > src/App.tsx << 'EOF'
function App() {
  return (
    <div className="bg-bg-page min-h-screen p-8 font-ui">
      <div className="bg-bg-card border border-border-subtle rounded-lg p-6 max-w-2xl shadow-elev-1">
        <h1 className="font-content text-h1 text-text-primary">TokenKnows · Bootstrap OK</h1>
        <p className="text-body text-text-muted mt-2">
          看到对的颜色 + serif 字体的标题 + Poppins 正文,token 链路就通了。
        </p>
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <button className="bg-accent-primary text-inverse-text px-4 py-2 rounded-md text-body-sm font-medium">
            主 CTA (陶土橙)
          </button>
          <span className="bg-success-bg text-success-dark px-2 py-0.5 rounded text-micro font-medium">
            success
          </span>
          <span className="bg-warning-bg text-warning px-2 py-0.5 rounded text-micro font-medium">
            warning
          </span>
          <span className="bg-danger-bg text-danger px-2 py-0.5 rounded text-micro font-medium">
            danger
          </span>
        </div>
        <p className="text-caption text-text-subtle mt-4 font-mono">
          下一步 → cat docs/engineering_handoff/tasks/T01-auth.md
        </p>
      </div>
    </div>
  )
}
export default App
EOF
echo "   ✓ src/App.tsx (token 验证页)"

# ─── 跑 build 验证 ────────────────────────────────────
say "build 验证 token 链路..."
BUILD_OUT=$(npm run build 2>&1)
if echo "$BUILD_OUT" | grep -qE "(✗|✘|Error |error TS)"; then
  echo "$BUILD_OUT" | tail -15
  die "build 失败"
fi

CSS_FILE=$(ls dist/assets/*.css 2>/dev/null | head -1)
[ -n "$CSS_FILE" ] || die "build 完没找到 CSS"

MATCHES=$(grep -oE "\.bg-bg-card|\.bg-accent-primary|\.text-text-primary|\.font-content" "$CSS_FILE" | sort -u | wc -l | tr -d ' ')

echo ""
echo -e "${G}════════════════════════════════════════${N}"
echo -e "${G}✓ 补全完成${N}"
echo -e "${G}════════════════════════════════════════${N}"
echo ""
echo "  Token class 验证: ${MATCHES}/4"
if [ "$MATCHES" -lt 4 ]; then
  echo -e "${Y}  ! 不足 4/4,可能 @config 指令没生效。看 src/index.css 顶部${N}"
else
  echo -e "${G}  ✓ 全部 token class 已编译${N}"
fi
echo ""
echo "  下一步 (在 $PROJECT_DIR):"
echo "    npm run dev"
echo "    浏览器打开 http://localhost:5173 应该看到 'TokenKnows · Bootstrap OK'"
echo ""
