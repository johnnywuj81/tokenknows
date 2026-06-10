# TokenKnows · Cursor 插件 v0

把 Cursor IDE 里的 AI 对话(user prompt + assistant reply)增量推送到 TokenKnows。

## 数据来源

Cursor 把对话存在 SQLite:

```
~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
```

表 `cursorDiskKV` 的两类 key:

| key 模式 | 含义 |
|---|---|
| `composerData:<convId>` | 对话元数据(createdAt / lastUpdatedAt / fullConversationHeadersOnly) |
| `bubbleId:<convId>:<bubbleId>` | 单个 turn 的内容(text / richText / context) |

`type=1`=user,`type=2`=assistant。

## 安装

```bash
pip install requests   # 唯一外部依赖
```

## 跑

```bash
# 一次:
python3 plugins/cursor/sync.py

# 限定项目 (按 workspaceRootUri 过滤):
python3 plugins/cursor/sync.py --filter-cwd ~/TokenKnows

# 持续监听 60s 轮询:
python3 plugins/cursor/sync.py --watch --filter-cwd ~/TokenKnows
```

state 存 `~/.tokenknows/cursor_state.json`:`{convId: lastUpdatedAt_ms}`。增量按对话级 `lastUpdatedAt` 推进,新 turn 才会再扫。

## 注意

- **读 sqlite 是 read-only**(`?mode=ro` URI),Cursor 在跑也安全
- bubble 没单独时间戳,统一用所在对话的 `lastUpdatedAt`(秒级有偏差,不影响业务)
- `richText` (ProseMirror JSON) 自动拍平成纯文本;assistant 没文本但有 `suggestedCodeBlocks` 时退化为 "(code suggestions: …)"
- 同一文本多次出现 → backend `content_hash` 去重(我跟 Cursor 重复说"你好"只入 1 条)

## 实测

```
conversations=13 bubbles=2920 events=1362 ingested=1331 skipped=31
```

13 个跟 Cursor 的对话,2920 个 turn,过滤掉无文本 + 去重后 1331 条入工作台。
