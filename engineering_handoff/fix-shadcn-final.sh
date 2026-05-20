#!/usr/bin/env bash
# 最后一击:
#  1. 展平 src/components/ui/ui/ → src/components/ui/
#  2. 建缺失的 src/lib/utils.ts (含 cn() helper)
#  3. 把 components.json aliases 改成相对路径 (防 shadcn 再创 @ 字面文件夹)
#  4. build 验证

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

# ─── 1. 展平双层 ui/ ─────────────────────────────────
echo -e "${G}▶${N} 检查并展平 src/components/ui/ui/..."
if [ -d src/components/ui/ui ]; then
  cp -R src/components/ui/ui/* src/components/ui/
  rm -rf src/components/ui/ui
  echo "    ✓ 已展平"
else
  echo "    - src/components/ui/ui 不存在,跳过(可能已经是正确结构)"
fi

# ─── 2. 建 src/lib/utils.ts ──────────────────────────
echo -e "${G}▶${N} 检查 src/lib/utils.ts..."
mkdir -p src/lib
if [ ! -f src/lib/utils.ts ]; then
  cat > src/lib/utils.ts << 'EOF'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
EOF
  echo "    ✓ 已创建 (含 cn() helper)"
else
  echo "    - 已存在,跳过"
fi

# ─── 3. components.json aliases 改相对路径 ──────────
echo -e "${G}▶${N} 修 components.json aliases (相对路径,防 shadcn 再踩坑)..."
if [ -f components.json ]; then
  python3 << 'PYEOF'
import json, sys
try:
    c = json.load(open('components.json'))
    c['aliases'] = {
        "components": "src/components",
        "utils": "src/lib/utils",
        "ui": "src/components/ui",
        "lib": "src/lib",
        "hooks": "src/hooks"
    }
    json.dump(c, open('components.json','w'), indent=2)
    print("    ✓ aliases 已改")
except Exception as e:
    print(f"    ! 改 components.json 失败: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
else
  echo "    ! components.json 不存在 (但不影响 build,跳过)"
fi

# ─── 4. 验证文件齐了 ─────────────────────────────────
COUNT=$(ls src/components/ui/*.tsx 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "=== src/components/ui/ ==="
ls src/components/ui/ | head -25 | sed 's/^/    /'
echo ""
echo "    总数: $COUNT 个 .tsx 文件"
echo ""
echo "=== src/lib/ ==="
ls src/lib/ | sed 's/^/    /'

if [ "$COUNT" -lt 15 ]; then
  echo -e "${R}✗ 组件数不足 15 个 ($COUNT 个),先解决这个再 build${N}"
  exit 1
fi

# ─── 5. 跑 build ─────────────────────────────────────
echo ""
echo -e "${G}▶${N} build 验证..."
BUILD_OUT=$(npm run build 2>&1)
if echo "$BUILD_OUT" | grep -qE "(error TS|Error \[ERR|✘ \[)"; then
  echo "$BUILD_OUT" | grep -E "error TS|Error \[|✘ \[" | head -10
  echo ""
  echo -e "${R}✗ build 失败,看上面具体错误${N}"
  echo ""
  echo "完整 build 输出:"
  echo "$BUILD_OUT" | tail -20
  exit 1
fi

echo "$BUILD_OUT" | tail -8

CSS_FILE=$(ls dist/assets/*.css 2>/dev/null | head -1)
TOKEN_MATCHES=$(grep -oE "\.bg-bg-card|\.bg-accent-primary|\.text-text-primary|\.font-content" "$CSS_FILE" 2>/dev/null | sort -u | wc -l | tr -d ' ')

# ─── 完成 ────────────────────────────────────────────
echo ""
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo -e "${G}✓ 全部完成 — 可以进入开发了${N}"
echo -e "${G}════════════════════════════════════════════════════════${N}"
echo ""
echo "    shadcn 组件:       $COUNT 个"
echo "    Token class:       $TOKEN_MATCHES/4"
echo "    Build:             ✓"
echo ""
echo "  下一步:"
echo "    cd $PROJECT_DIR"
echo "    npm run dev       # 看页面正常"
echo ""
echo "    # 另开终端:"
echo "    cd $PROJECT_DIR"
echo "    claude            # 启动 Claude Code,自动读 CLAUDE.md"
echo ""
echo "    # 第一句:"
echo "    > 请按 docs/engineering_handoff/tasks/T01-auth.md 实现 T01 认证流程"
echo ""
