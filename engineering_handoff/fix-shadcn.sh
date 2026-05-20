#!/usr/bin/env bash
# 把 components.json 从 radix-nova 换回 new-york 经典 style,
# 然后强制 add 21 个组件。

set -e
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'

PROJECT_DIR="$HOME/TokenKnows/code/tokenknows-web"
[ -d "$PROJECT_DIR" ] || { echo -e "${R}✗ $PROJECT_DIR 不存在${N}"; exit 1; }

if [ -d "$HOME/.nvm" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || true
fi

cd "$PROJECT_DIR"
echo -e "${G}▶${N} 当前 node: $(node -v)"

# 1. 备份旧 components.json
if [ -f components.json ]; then
  mv components.json components.json.radix-nova.bak
  echo -e "${G}▶${N} 旧 components.json 备份为 components.json.radix-nova.bak"
fi

# 2. 写经典 new-york style 的 components.json
cat > components.json << 'EOF'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
EOF
echo -e "${G}▶${N} 新 components.json 写好 (style=new-york, baseColor=neutral)"

# 3. 确保目录存在
mkdir -p src/components/ui src/lib

# 4. 强制装组件
echo -e "${G}▶${N} 装 21 个组件 (可能需要 1-2 分钟)..."
npx --yes shadcn@latest add \
  button card input label dialog drawer dropdown-menu \
  badge tabs separator avatar progress switch tooltip \
  select textarea checkbox radio-group scroll-area sheet skeleton \
  --overwrite --yes

# 5. 验证
COUNT=$(ls src/components/ui/*.tsx 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo -e "${G}════════════════════════════════════════${N}"
if [ "$COUNT" -ge 15 ]; then
  echo -e "${G}✓ shadcn 修复成功${N}"
  echo -e "${G}════════════════════════════════════════${N}"
  echo ""
  echo "  src/components/ui/ 下文件:"
  ls src/components/ui/*.tsx | xargs -n1 basename | sed 's/^/    /'
  echo ""
  echo "  共 $COUNT 个组件"
else
  echo -e "${R}✗ 还是只有 $COUNT 个组件${N}"
  echo -e "${R}════════════════════════════════════════${N}"
  echo ""
  echo "  调试建议:"
  echo "    cd $PROJECT_DIR"
  echo "    npx shadcn@latest add button --overwrite -y"
  echo "    # 看实际输出有没有真的报错"
  echo ""
  echo "  或者用 @canary 版试试:"
  echo "    npx shadcn@canary add button -y"
fi
