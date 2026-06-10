# TokenKnows · Codex 插件 v0

把你跟 **OpenAI Codex**(CLI / Desktop)的每次会话(user / assistant turn + 工具调用)增量推到 TokenKnows 后端,出现在工作台事件流里。

镜像 `claude-code` 插件,适配 Codex 的 rollout JSONL 格式。

## 数据来源

```
~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<ts>-<uuid>.jsonl   ← 每次会话一个
~/.codex/archived_sessions/rollout-*.jsonl                     ← 归档 (--include-archived 才扫)
```

每个 rollout:首行 `session_meta`(含 `cwd` / session id / model),其后 `response_item`。
插件提取:

| rollout 内容 | → Event | 备注 |
|---|---|---|
| `message` role=user | `ai_conversation_turn` | 跳过注入的 AGENTS.md / `<INSTRUCTIONS>` / `<environment_context>` 等 |
| `message` role=assistant | `ai_conversation_turn` | |
| `message` role=developer | (跳过) | 系统提示噪声 |
| `function_call` / `custom_tool_call` | `tool_call` | 工具名 + 参数 |
| `reasoning`(加密)/ `*_output` / `event_msg` | (跳过) | |

`source_type=codex`,`source_ref=session.cwd`(项目路径)。

## 安装

```bash
pip install requests   # 唯一外部依赖
```

## 验证(先 dry-run, 不写库)

```bash
python3 plugins/codex/sync.py --dry-run --include-archived
# 只解析+打印每个 rollout 会产出多少 event, 不 POST, 不推进 offset
```

## 一次性跑

```bash
python3 plugins/codex/sync.py \
  --backend http://127.0.0.1:8001 \
  --project proj-demo-001
```

state 存 `~/.tokenknows/codex_sync_state.json`,下次只跑增量。

## ⚠️ 限定项目(强烈建议)

Codex 会话按 `cwd` 跨多个项目。**不加过滤会把所有项目的 codex 历史混进一个
project**。只采某个项目:

```bash
python3 plugins/codex/sync.py \
  --watch \
  --filter-cwd ~/TokenKnows
```

## 持续监听

```bash
python3 plugins/codex/sync.py --watch   # 每 30s 扫一次增量
```

## 后台跑(macOS launchd)

随其它插件一起装(见 `scripts/launchd/install.sh`,已含 `codex` label):

```bash
./scripts/launchd/install.sh
launchctl list | grep com.tokenknows.codex
tail -f ~/Library/Logs/tokenknows/codex.log
```

默认 launchd 配置**不带 `--filter-cwd`**(采全部 codex 会话)。若只想采特定项目,
在 `~/Library/LaunchAgents/com.tokenknows.codex.plist` 的 `ProgramArguments` 里
加 `--filter-cwd /path` 后 `launchctl unload + load`。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--backend` | env `TOKENKNOWS_API_BASE` / `http://127.0.0.1:8001` | 后端基址 |
| `--project` | env `TOKENKNOWS_DEFAULT_PROJECT` / `proj-demo-001` | 目标 project_id |
| `--sessions-dir` | `~/.codex/sessions` | 会话目录 |
| `--filter-cwd` | (无) | 只采 session cwd 匹配的会话 |
| `--include-archived` | off | 也扫 `~/.codex/archived_sessions` |
| `--dry-run` | off | 只解析统计,不 POST,不推进 offset |
| `--watch` | off | 持续模式,30s 轮询 |
| `--reset` | off | 清空 state 全量重推(慎用) |
