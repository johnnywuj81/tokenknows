#!/usr/bin/env bash
# 一次性修复: 干掉 ~/.local/bin/{node,npm,npx} 这几个指向 Homebrew node@18 的 symlink,
# 然后用 nvm 22 跑 bootstrap。备份不删除,以后可恢复。

set -e
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'

echo -e "${G}1.${N} 加载 nvm 并切到 22..."
if [ ! -s "$HOME/.nvm/nvm.sh" ]; then
  echo -e "${R}✗ nvm 未安装。先 curl 装 nvm${N}"
  exit 1
fi
. "$HOME/.nvm/nvm.sh"
nvm use 22 || nvm install 22
nvm alias default 22 >/dev/null

echo -e "${G}2.${N} 备份冲突的 symlink..."
for bin in node npm npx; do
  src="$HOME/.local/bin/$bin"
  if [ -L "$src" ] || [ -f "$src" ]; then
    dst="$src.v18.symlink.bak.$(date +%s)"
    mv "$src" "$dst"
    echo "   $src → $(basename $dst)"
  fi
done

echo -e "${G}3.${N} 刷新 bash 命令缓存..."
hash -r

echo -e "${G}4.${N} 验证 node 路径..."
which node
node -v
NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 20 ]; then
  echo -e "${R}✗ node 还是 $NODE_MAJOR,可能 PATH 里还有别的捣乱${N}"
  echo "PATH 前 8 项:"
  echo "$PATH" | tr ':' '\n' | head -8 | sed 's/^/   /'
  exit 1
fi

echo -e "${G}5.${N} 跑 bootstrap..."
echo ""
cd "$(dirname "$0")"
./bootstrap-step1-3.sh "$HOME/TokenKnows/code" 2>&1 | tee bootstrap.log
RC=${PIPESTATUS[0]}

echo ""
if [ "$RC" -eq 0 ]; then
  echo -e "${G}════════════════════════════════════════${N}"
  echo -e "${G}✓ 全部完成${N}"
  echo -e "${G}════════════════════════════════════════${N}"
else
  echo -e "${R}════════════════════════════════════════${N}"
  echo -e "${R}✗ bootstrap 失败,看上面输出${N}"
  echo -e "${R}════════════════════════════════════════${N}"
  exit $RC
fi
