# TokenKnows · Claude Code 插件 v0

把你跟 Claude Code 的每次对话(user / assistant turn + tool 调用)增量推到 TokenKnows 后端,出现在工作台事件流里。

## 安装

```bash
pip install requests   # 唯一外部依赖
```

## 一次性跑

```bash
python3 plugins/claude-code/sync.py \
  --backend http://localhost:8001 \
  --project proj-demo-001
```

会扫 `~/.claude/projects/*/<session>.jsonl` 所有会话,把 user / assistant turn 投到 backend。state 存在 `~/.tokenknows/sync_state.json`,下次只跑增量。

## 持续监听(推荐)

```bash
python3 plugins/claude-code/sync.py --watch
# 每 30s 扫一次, ctrl-c 退出
```

## 限定项目

只采当前项目的会话(根据 `cwd` 过滤):

```bash
python3 plugins/claude-code/sync.py \
  --watch \
  --filter-cwd ~/TokenKnows
```

## 后台跑(macOS launchd)

```bash
cat > ~/Library/LaunchAgents/com.tokenknows.claude-sync.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tokenknows.claude-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$HOME/TokenKnows/plugins/claude-code/sync.py</string>
    <string>--watch</string>
    <string>--filter-cwd</string>
    <string>$HOME/TokenKnows</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/tk-claude-sync.log</string>
  <key>StandardErrorPath</key><string>/tmp/tk-claude-sync.err</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.tokenknows.claude-sync.plist
```

## 重置(全量重推)

如果改了去重逻辑想重新跑一遍:

```bash
python3 plugins/claude-code/sync.py --reset
```

## 数据流

```
~/.claude/projects/<dir>/<session>.jsonl
            ↓ scan (file mtime + line offset)
       parse user / assistant turn
            ↓ jsonl_entry_to_event()
       Event { source_type:claude_code, content_hash:sha256 }
            ↓ POST /api/v1/projects/:id/events (≤200/批)
       后端按 (project_id, content_hash) 幂等去重
            ↓
       SQLite events 表 → 工作台事件流
```

## 注意

- **content_hash** 用 `sha256(text)` 做去重 key, 同样内容多次跑只入 1 条
- **filter-cwd** 不严格: Claude Code 的 cwd 是 turn 级别记的, 跨项目对话可能漏
- 投递失败不阻塞下次, state 仍前进 (避免无限重试相同坏行)
- v1 计划: 增加 tool_call 详细解析 + GitHub PR 推送的 commit/PR 事件
