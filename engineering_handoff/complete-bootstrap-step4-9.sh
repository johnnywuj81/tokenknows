#!/usr/bin/env bash
# Bootstrap 第 4-9 节自动化:
#   4. shadcn/ui 初始化 + 加常用组件 (有 fallback 防止 registry 鉴权问题)
#   5. Google Fonts (Lora / Poppins / JetBrains Mono)
#   6. 目录结构 (src/features/* 等)
#   7. React Router 占位 + main.tsx (含 QueryClient + MSW)
#   8. MSW 初始化 + 第一个 /me handler
#   9. 软链 mockups + docs + 复制 CLAUDE.md

set -e
export NPM_CONFIG_YES=true   # 全局自动 yes,避免 npx 装包时卡 prompt

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
say()  { echo -e "${G}▶${N} $1"; }
warn() { echo -e "${Y}!${N} $1"; }
die()  { echo -e "${R}✗${N} $1"; exit 1; }

PROJECT_DIR="$HOME/TokenKnows/code/tokenknows-web"
HANDOFF_DIR="$(cd "$(dirname "$0")" && pwd)"
TOKENKNOWS_DIR="$HOME/TokenKnows"

[ -d "$PROJECT_DIR" ] || die "找不到 $PROJECT_DIR — 先跑 bootstrap-step1-3.sh + complete-bootstrap.sh"
[ -f "$PROJECT_DIR/tailwind.config.ts" ] || die "tailwind.config.ts 不在 — complete-bootstrap.sh 没跑成功"

# 加载 nvm
if [ -d "$HOME/.nvm" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || true
fi

cd "$PROJECT_DIR"
say "在 $PROJECT_DIR · node $(node -v)"

# 关掉残留 vite (5173-5175)
for port in 5173 5174 5175; do
  lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
done

# ─── 第 4 节: shadcn/ui ──────────────────────────────
say "[4] 装 shadcn/ui..."

SHADCN_OK=false
if [ ! -f components.json ]; then
  echo "   尝试 npx shadcn@latest init -t vite -p nova -y..."
  if npx --yes shadcn@latest init -t vite -p nova -y --silent 2>&1 | tee /tmp/shadcn-init.log | tail -10; then
    if [ -f components.json ]; then
      SHADCN_OK=true
      echo "   ✓ shadcn init 成功"
    fi
  fi

  if [ "$SHADCN_OK" = false ]; then
    warn "shadcn init 失败 (常见: 'Not authorized' 鉴权问题或网络),走手动 fallback..."

    # 手动建 components.json + utils.ts
    mkdir -p src/lib src/components/ui
    cat > src/lib/utils.ts << 'EOF'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
EOF

    cat > components.json << 'EOF'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "stone",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui"
  }
}
EOF
    echo "   ✓ 手动建好 components.json + src/lib/utils.ts"
  fi
else
  echo "   - components.json 已存在,跳过 init"
  SHADCN_OK=true
fi

# 加常用组件
say "[4] 加常用组件 (button card input label dialog drawer ...)"
COMPONENTS="button card input label dialog drawer dropdown-menu badge tabs separator avatar progress switch tooltip form select textarea checkbox radio-group scroll-area sheet"

ADD_OK=false
if npx --yes shadcn@latest add $COMPONENTS -y --silent 2>&1 | tail -5; then
  ADD_OK=true
  COMP_COUNT=$(ls src/components/ui/ 2>/dev/null | wc -l | tr -d ' ')
  echo "   ✓ src/components/ui/ 下有 $COMP_COUNT 个组件文件"
fi

if [ "$ADD_OK" = false ] || [ "$(ls src/components/ui/ 2>/dev/null | wc -l)" -lt 5 ]; then
  warn "shadcn add 拿不到组件 (registry 鉴权 / 网络问题)"
  warn "已建好 components.json,你可以稍后单独跑: npx shadcn@latest add button card ..."
  warn "或者从 https://ui.shadcn.com/docs/components 手动复制组件源码到 src/components/ui/"
fi

# ─── 第 5 节: 字体 ────────────────────────────────────
say "[5] 装 Google Fonts (Lora + Poppins + JetBrains Mono)..."
if ! grep -q "fonts.googleapis.com" index.html; then
  # 在 </head> 前插入字体链接
  python3 << 'PYEOF'
with open('index.html') as f:
    html = f.read()
fonts = '''    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&family=Poppins:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
'''
html = html.replace('</head>', fonts + '  </head>')
with open('index.html', 'w') as f:
    f.write(html)
print("   ✓ 字体链接已加到 index.html")
PYEOF
else
  echo "   - 字体链接已存在,跳过"
fi

# ─── 第 6 节: 目录结构 ────────────────────────────────
say "[6] 建业务目录..."
mkdir -p src/features/{auth,projects,workbench,events,documents,evidence,generation,review,redaction,publish,settings,admin}
mkdir -p src/{components/shared,hooks,mocks,routes,stores,types}

for d in features components/shared hooks mocks routes stores types; do
  [ -f "src/$d/README.md" ] || echo "# $d" > "src/$d/README.md"
done
echo "   ✓ src/features (12) + src/{components/shared,hooks,mocks,routes,stores,types}"

# ─── 第 7 节: React Router + main.tsx ────────────────
say "[7] 写 React Router 占位 + 升级 main.tsx..."

cat > src/routes/index.tsx << 'EOF'
import { createBrowserRouter } from 'react-router-dom'

// 占位路由 — 每屏完成后填入对应 component (lazy 加载)
export const router = createBrowserRouter([
  { path: '/',                                element: <div>Workbench placeholder (TODO: T03)</div> },
  { path: '/login',                           element: <div>Login (TODO: T01)</div> },
  { path: '/register',                        element: <div>Register (TODO: T01)</div> },
  { path: '/verify-email',                    element: <div>Verify email (TODO: T01)</div> },
  { path: '/forgot-password',                 element: <div>Forgot password (TODO: T01)</div> },
  { path: '/reset-password',                  element: <div>Reset password (TODO: T01)</div> },
  { path: '/projects/new',                    element: <div>New project (TODO: T02)</div> },
  { path: '/projects/:id',                    element: <div>Project workbench (TODO: T03)</div> },
  { path: '/projects/:id/documents',          element: <div>Document list (TODO: T05)</div> },
  { path: '/projects/:id/documents/:docId',   element: <div>Document page (TODO: T06)</div> },
  { path: '/projects/:id/documents/:docId/review',     element: <div>Review (TODO: T09)</div> },
  { path: '/projects/:id/documents/:docId/redaction',  element: <div>Redaction (TODO: T10)</div> },
  { path: '/projects/:id/documents/:docId/published/:publishId', element: <div>Publish receipt (TODO: T12)</div> },
  { path: '/projects/:id/settings',           element: <div>Project settings (TODO: T13 v0.2)</div> },
  { path: '/admin',                           element: <div>Admin (TODO: T15 v0.2)</div> },
])
EOF
echo "   ✓ src/routes/index.tsx (含全部 15 屏路由占位)"

cat > src/main.tsx << 'EOF'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { router } from './routes'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } }
})

async function enableMocking() {
  if (!import.meta.env.DEV) return
  const { worker } = await import('./mocks/browser')
  return worker.start({ onUnhandledRequest: 'bypass' })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>
  )
})
EOF
echo "   ✓ src/main.tsx (StrictMode + QueryClient + Router + MSW init)"

# ─── 第 8 节: MSW ─────────────────────────────────────
say "[8] 初始化 MSW + 第一个 /me handler..."

if [ ! -f public/mockServiceWorker.js ]; then
  npx --yes msw init public/ --save 2>&1 | tail -3
fi
[ -f public/mockServiceWorker.js ] && echo "   ✓ public/mockServiceWorker.js"

cat > src/mocks/browser.ts << 'EOF'
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)
EOF

cat > src/mocks/handlers.ts << 'EOF'
import { http, HttpResponse } from 'msw'

/**
 * MSW handlers — 后端 API 契约。
 * 后端实现按这个 mock 走;前端开发期全部走 mock。
 * 完整 API 清单见 docs/TDD.md §6.1
 */
export const handlers = [
  // 当前用户
  http.get('/api/v1/me', () =>
    HttpResponse.json({
      id: 'u1',
      email: 'dev@local',
      display_name: '开发者',
      email_verified: true,
      role: 'admin',
    })
  ),
]
EOF
echo "   ✓ src/mocks/{browser,handlers}.ts"

# ─── 第 9 节: 软链 + 复制 CLAUDE.md ──────────────────
say "[9] 软链 mockups / docs + 复制 CLAUDE.md..."

mkdir -p docs
# 用绝对路径,跨机器可移植
ln -sfn "$TOKENKNOWS_DIR/mockups"                            docs/mockups
ln -sfn "$TOKENKNOWS_DIR/engineering_handoff"                docs/engineering_handoff
ln -sfn "$TOKENKNOWS_DIR/PRD_TokenKnows_MVP.md"              docs/PRD.md
ln -sfn "$TOKENKNOWS_DIR/TDD_TokenKnows_MVP.md"              docs/TDD.md
ln -sfn "$TOKENKNOWS_DIR/DesignHandoff_TokenKnows_MVP.md"    docs/DesignHandoff.md
ln -sfn "$TOKENKNOWS_DIR/figma_handoff"                      docs/figma_handoff
echo "   ✓ docs/{mockups,engineering_handoff,PRD.md,TDD.md,DesignHandoff.md,figma_handoff}"

cp "$HANDOFF_DIR/CLAUDE.md" ./CLAUDE.md
echo "   ✓ CLAUDE.md 已放到仓库根 (Claude Code 启动后自动加载)"

# ─── 给 .gitignore 加几条 ────────────────────────────
if [ -f .gitignore ]; then
  for pat in "/dist" "/node_modules" "/.env" ".DS_Store" "complete*.log" "bootstrap*.log"; do
    grep -qxF "$pat" .gitignore || echo "$pat" >> .gitignore
  done
  echo "   ✓ .gitignore 补全"
fi

# ─── git init (如果还没) ─────────────────────────────
if [ ! -d .git ]; then
  say "git init + 首次 commit..."
  git init -q
  git add -A
  git commit -q -m "T00: bootstrap — Vite 8 + React 19 + Tailwind v4 + shadcn + MSW + Router" || true
  echo "   ✓ git 初始化 + 首次 commit"
fi

# ─── 最终 build 验证 ────────────────────────────────
say "build 验证完整链路..."
BUILD_OUT=$(npm run build 2>&1)
if echo "$BUILD_OUT" | grep -qE "(error TS|Error \[)"; then
  echo "$BUILD_OUT" | tail -15
  die "build 失败,看上面输出"
fi

CSS_FILE=$(ls dist/assets/*.css 2>/dev/null | head -1)
TOKEN_MATCHES=$(grep -oE "\.bg-bg-card|\.bg-accent-primary|\.text-text-primary|\.font-content" "$CSS_FILE" 2>/dev/null | sort -u | wc -l | tr -d ' ')
COMP_COUNT=$(ls src/components/ui/ 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo -e "${G}✓ 第 4-9 节全部完成${N}"
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo ""
echo "  仓库: $PROJECT_DIR"
echo "  Token class 验证: $TOKEN_MATCHES/4"
echo "  shadcn 组件:      $COMP_COUNT 个"
echo "  软链:             docs/ 下 6 个"
echo "  CLAUDE.md:        ✓ 在仓库根"
echo "  Git:              $(git log --oneline 2>/dev/null | wc -l | tr -d ' ') 个 commit"
echo ""
if [ "$COMP_COUNT" -lt 10 ]; then
  echo -e "${Y}  ! shadcn 组件不足 10 个 — 可能 'shadcn add' 时网络失败${N}"
  echo -e "${Y}    手动补:${N}"
  echo "    cd $PROJECT_DIR"
  echo "    npx shadcn@latest add button card input dialog drawer badge tabs"
  echo ""
fi
echo "  下一步:"
echo "    cd $PROJECT_DIR"
echo "    npm run dev          # 验证页面正常"
echo "    claude               # 启动 Claude Code,自动读 CLAUDE.md"
echo ""
echo "  第一个任务:"
echo "    > 请按 docs/engineering_handoff/tasks/T01-auth.md 实现 T01 认证流程"
echo ""
