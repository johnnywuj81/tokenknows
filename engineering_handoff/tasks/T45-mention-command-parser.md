# T45 · @ 机器人命令解析 + 限频 + Schema 扩展

> v0.5.0 第一块。M5 @ 机器人按需触发的基础设施。
> Proposal: [v0.5 §2.1 命令规格 / §2.3 数据模型 / OD-1 / OD-3 / OD-4](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
让 IM 群消息中 `@TokenKnows /distill 2h` 这种自然命令可被解析为结构化触发请求，并在用户层面限频。是 T46 MentionDispatcher 的前置。

## 2. 范围
- **In**: `parse_command(text)` 严格 whitelist 解析、Redis-backed 限频、`TriggerSignal.type='im_mention'` schema 扩展、单元测试
- **Out**: 实际从 IM 群拉消息（T46）、调用 dispatcher（T46）、群内回执（T47）

## 3. 命令文法 (OD-1)

```
@TokenKnows <subcommand> <window>

subcommand ∈ {distill, digest, skill}
window     ∈ {30m, 2h, today, yesterday, 7d}   ← OD-4 仅 5 预设
```

非法 case 全部拒绝（不允许 `2.5h` 等自由值，避免恶意拉满群历史）。

## 4. 数据契约

```python
# app/services/auto_trigger/mention_dispatcher.py

from dataclasses import dataclass
from typing import Literal

Subcommand = Literal["distill", "digest", "skill"]
WindowPreset = Literal["30m", "2h", "today", "yesterday", "7d"]

@dataclass(frozen=True)
class ParsedMention:
    subcommand: Subcommand
    window: WindowPreset
    raw_text: str  # 审计用

class ParseError(Exception):
    """命令文法错; raise 后 dispatcher 在群里回简短帮助."""

def parse_command(text: str) -> ParsedMention: ...
def check_rate_limit(chat_id: str, user_id: str) -> bool: ...  # True=允许
```

`TriggerSignal.payload` 扩展（与现有 type='cron'/'github_webhook' 同源）：
```json
{
  "type": "im_mention",
  "summary": "@TokenKnows /digest 2h · 后端技术群 · by alice",
  "event_id": "msg-om_xxx",
  "payload": {
    "command": "digest",
    "window": "2h",
    "im_chat_id": "oc_xxx",
    "triggered_by_user_id": "ou_alice",
    "message_id": "om_xxx"
  }
}
```

## 5. 限频规则 (OD-3)

| 维度 | 阈值 |
|---|---|
| 每群每用户 | 5 分钟内最多 1 次 |
| 每群所有用户 | 1 小时内最多 6 次 |

实现：Redis `SETEX` key `mention:{chat_id}:{user_id}` TTL=300 / `mention:{chat_id}:hour` 滚动 counter。Redis 不可用时降级到内存 dict（v0.5.0 单实例可接受）。

## 6. 组件分解

```
backend/app/services/auto_trigger/
├── mention_dispatcher.py        ← T45 文件 (parse + rate_limit 部分)
│   ├── ParseError
│   ├── ParsedMention
│   ├── parse_command(text) → ParsedMention
│   ├── window_to_timedelta(window) → timedelta (30m=30min / 2h=2h / today=今晨0点 / 7d=7d)
│   └── check_rate_limit(chat_id, user_id) → tuple[bool, reason]
└── (T46 后续在此文件加 dispatch_mention)

backend/tests/test_mention_command.py            ← 单测
```

## 7. 必备状态（DoD）
- [ ] `parse_command("@TokenKnows /distill 2h")` → `ParsedMention(subcommand='distill', window='2h')`
- [ ] 缺 subcommand / window 非预设 / 多余 token → `ParseError`
- [ ] 限频：1 分钟内同 user 2 次调用 → 第 2 次 False，reason="rate_limit_per_user_5min"
- [ ] `window_to_timedelta` 5 个预设全覆盖（含 `today`/`yesterday` 跨日边界）

## 8. 验收
- [ ] 解析器单测 ≥ 12 case（happy + 5 个 subcommand × window 组合 + 6 个非法）
- [ ] 限频测试覆盖：单用户 + 同群多用户 + 跨群同用户
- [ ] `today`/`yesterday` 边界：00:01 调 today 返当天 0 点 → now，调 yesterday 返昨天 0 点 → 昨天 23:59
- [ ] Schema 扩展兼容现有 `trigger_executions.signal.type` 字段（v0.4 已有的不破坏）

## 9. 已知陷阱
- 不要用 regex 解析（写脆），用 `text.split()` + whitelist 比对最稳
- @ 提及在飞书是 `<at user_id="..."></at>` XML 节点，钉钉是 `@TokenKnows` 文本 — 提取 mention 由 T46 处理；本任务只接受**已剥离 @ 部分**的 plain command text
- `/digest 2h` 与 `/digest  2h`（多空格）应等效（`text.split()` 默认压缩）
- 时区：`today` 用项目所在时区（v0.5.0 暂硬编码 Asia/Shanghai，与 APScheduler 一致）
- Redis 失败兜底：用 module-level `defaultdict(deque)` 内存 fallback；进程重启丢限频记录不致命

## 10. Claude Code 指令
先写 `parse_command` 纯函数 + 完整单测（不依赖任何 IO）→ 再写 `check_rate_limit`（注入 Redis client，测试时用 fakeredis）→ 最后扩 TriggerSignal schema 字段。不要在 T45 内实现 dispatch 流程（留 T46）。
