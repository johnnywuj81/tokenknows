#!/usr/bin/env bash
# 打包 tokenknows-mcp PyPI 发行版.
# 源码真身在 ../tokenknows-api/mcp_server (单一事实源);
# 本脚本在构建时把它拷贝进来 (mcp_server/ 在 .gitignore 里, 不入库).
set -euo pipefail
cd "$(dirname "$0")"

rm -rf mcp_server dist
rsync -a --exclude='__pycache__' ../tokenknows-api/mcp_server/ mcp_server/
uv build
echo "✓ dist ready: $(ls dist)"
