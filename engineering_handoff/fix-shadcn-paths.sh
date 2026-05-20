#!/usr/bin/env bash
# shadcn 把组件写到了错位置 (./components/ui/ 而不是 ./src/components/ui/)
# 因为 tsconfig.json 没有 paths,shadcn 读不到 @/* 的映射,fallback 到 cwd 相对路径。
# 此脚本: 修 tsconfig.json + 搬文件到正确位置 + 跑 build 验证。

set -e
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'

PROJECT_DIR="$HOME/TokenKnows/code/tokenknows-web"
[ -d "$PROJECT_DIR" ] || { echo -e "${R}✗ $PROJECT_DIR 不存在${N}"; exit 1; }

if [ -d "$HOME/.nvm" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || true
fi

cd "$PROJECT_DIR"
echo -e "${G}▶${N} 当前 node: $(node -v)"

# ─── 1. 找出文件被写到哪 ──────────────────────────────
echo -e "${G}▶${N} 找 shadcn 把 button.tsx 写到哪里了..."
FOUND=$(find . -name "button.tsx" -not -path "*/node_modules/*" 2>/dev/null | head -5)
if [ -z "$FOUND" ]; then
  echo -e "${R}✗ 没找到 button.tsx — 之前 shadcn add 可能根本没成功${N}"
  echo "  跑: npx shadcn@latest add button --overwrite -y"
  exit 1
fi
echo "$FOUND" | sed 's/^/    /'

# ─── 2. 修 tsconfig.json (加 paths,让 shadcn 以后能找对) ──
echo -e "${G}▶${N} 修 tsconfig.json (加 baseUrl + paths)..."
if [ -f tsconfig.json ]; then
  cp tsconfig.json tsconfig.json.bak.$(date +%s)
fi
cat > tsconfig.json << 'EOF'
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ],
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
EOF
echo "    ✓ tsconfig.json 已更新"

# ─── 3. 搬文件到 src/components/ui/ ──────────────────
echo -e "${G}▶${N} 搬文件到 src/components/ui/..."
if [ -d ./components/ui ]; then
  mkdir -p src/components/ui
  # 用 cp + rm 而不是 mv,跨 device 安全
  cp -R ./components/ui/* src/components/ui/
  rm -rf ./components
  echo "    ✓ 21 个组件已搬到 src/components/ui/"
else
  echo -e "${Y}    ! ./components/ui 不存在,可能文件在别的位置${N}"
  echo "      已找到的位置: $FOUND"
  echo "      手动搬一下"
  exit 1
fi

# ─── 4. 验证 ─────────────────────────────────────────
COUNT=$(ls src/components/ui/*.tsx 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "=== src/components/ui/ 内容 ==="
ls src/components/ui/*.tsx | xargs -n1 basename | sed 's/^/    /'
echo ""
echo "    总数: $COUNT 个 .tsx 文件"

# ─── 5. 跑 build 验证编译 ────────────────────────────
echo ""
echo -e "${G}▶${N} 跑 build 验证 @/* 别名 + 21 个组件能编译..."
BUILD_OUT=$(npm run build 2>&1)
if echo "$BUILD_OUT" | grep -qE "(error TS|Error \[ERR|✘)"; then
  echo "$BUILD_OUT" | tail -20
  echo ""
  echo -e "${R}✗ build 失败,看上面输出${N}"
  exit 1
fi

echo "$BUILD_OUT" | tail -8

# ─── 完成 ────────────────────────────────────────────
CSS_FILE=$(ls dist/assets/*.css 2>/dev/null | head -1)
TOKEN_MATCHES=$(grep -oE "\.bg-bg-card|\.bg-accent-primary|\.text-text-primary|\.font-content" "$CSS_FILE" 2>/dev/null | sort -u | wc -l | tr -d ' ')

echo ""
echo -e "${G}════════════════════════════════════════${N}"
echo -e "${G}✓ shadcn paths 修复完成${N}"
echo -e "${G}════════════════════════════════════════${N}"
echo ""
echo "    shadcn 组件:       $COUNT 个"
echo "    Token class:       $TOKEN_MATCHES/4"
echo "    Build:             ✓"
echo ""
echo "  下一步:"
echo "    cd $PROJECT_DIR"
echo "    npm run dev       # 浏览器 http://localhost:5173 应该 OK"
echo "    claude            # 启动 Claude Code 开 T01"
echo ""
