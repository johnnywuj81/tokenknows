#!/usr/bin/env bash
# 卸载 TokenKnows 4 个插件 LaunchAgent.
# 日志保留在 ~/Library/Logs/tokenknows/ 供事后排查.

set -euo pipefail

LAUNCH_DIR="$HOME/Library/LaunchAgents"

echo "─── TokenKnows LaunchAgent 卸载 ───"

for label in claude-code github cursor local-docs; do
    plist="$LAUNCH_DIR/com.tokenknows.$label.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm "$plist"
        echo "  ✓ removed com.tokenknows.$label"
    else
        echo "  · not installed: com.tokenknows.$label"
    fi
done

echo ""
echo "─── 卸载完成 ───"
echo "日志保留在: $HOME/Library/Logs/tokenknows/"
echo "彻底清理: rm -rf $HOME/Library/Logs/tokenknows/ ~/.tokenknows/"
