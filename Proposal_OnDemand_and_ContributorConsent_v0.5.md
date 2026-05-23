# Proposal · TokenKnows v0.5 · @ 机器人按需触发 + Skill 蒸馏 Contributor 个人确认

> 聚焦提案：补齐 v0.4 留下的两块拼图 —— **M5 即时触发** 与 **Skill 个人确认**（Q5 决策）。把"自动触发"从 4/5 模式完整为 5/5；同时把"自动蒸馏"从"系统决定"升级为"contributor 知情同意"。

---

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | TokenKnows v0.5 · @ 机器人按需 + Contributor 个人确认 产品技术方案 |
| 文档版本 | v0.5-draft.1（起草中） |
| 文档状态 | 起草中 · 待用户评审 |
| 撰写日期 | 2026-05-23 |
| 关联文档 | [v0.4 Proposal](./Proposal_Automatic_Generation_Trigger_v0.4.md) §13.5 / §14 Q5 · [v0.3 IM Proposal](./Proposal_IM_KnowledgeDistillation_v0.3.md) §6.3 / §7.4 IM-D |
| 目标读者 | 产品、研发、合规 |
| 体例 | PRD + TDD 一体 |

### 1.1 与 v0.3 / v0.4 的关系

| 维度 | v0.3 IM | v0.4 Auto-Trigger | **v0.5 本提案** |
| --- | --- | --- | --- |
| 触发模式 | 仅手动 + 个人助理 | M1-M4 全做了，M5 留 | **补 M5 @ 机器人按需** |
| Skill 蒸馏 | 用户传 chapter_ids 手动 | T42 阈值自动蒸馏 | **加 contributor 个人确认闸门**（Q5）|
| IM 群消息接入 | v0.3 已读 / v0.3.1 完整存档 | 仅消费 SignalGate 数据 | **新增"@ 提及"事件订阅** |
| 通知渠道 | web SSE | web SSE + 浮动通知卡 | **+ IM DM 通知**（contributor 同意流程） |

### 1.2 关键决策表

| # | 决策 | 取值 | 备注 |
| --- | --- | --- | --- |
| OD-1 | 命令语法 | **`@TokenKnows /distill <window>`** + 3 个 subcommand（`/digest` / `/skill` / `/distill`） | 与现有 IM bot 文化对齐；window 默认 `2h` |
| OD-2 | 触发权限 | **群内任意成员** 可触发；蒸馏归属当前项目 + 触发者作 created_by | 不限管理员；触发记入 audit_log |
| OD-3 | 限频 | **每群每用户 5 分钟内最多 1 次** / 每群每小时最多 6 次 | 防止刷屏 |
| OD-4 | 时间窗口范围 | **30m / 2h / today / yesterday / 7d**（5 个预设） | 不允许任意时间窗口（防恶意拉满群历史） |
| OD-5 | 回执方式 | **机器人在群里回 thread 消息**：`[Demo 草稿] 已生成 N 段, 查看: https://tokenknows.../assets/:id` | 不发 DM, 保持群内透明 |
| OD-6 | Contributor 同意期 | **30 天**（与 v0.3 同意书撤回期一致） | 超期 → status=`expired_no_consent` |
| OD-7 | Contributor 通知渠道 | **IM DM**（首选）+ **web 内 notification**（兜底） | DM 失败时仅 web，触发邮件留 v0.5.1 |
| OD-8 | 同意书原子粒度 | **每个 skill 一次确认**（不是"一次确认所有未来 skill"） | 与 Q5 决策"必须个人确认"对齐 |
| OD-9 | 拒绝后行为 | skill 标 `rejected_by_contributor`；30 天后归档 + 不再尝试同主题蒸馏 | 防止系统反复打扰用户 |
| OD-10 | 多 contributor 场景 | **全员同意**才能 active；任一拒绝 → skill 拒绝 | 与 Q5 决策一致（保守路径） |

---

## 2. 模块 A · @ 机器人按需触发（M5）

> Proposal v0.4 §4 M5 模式 + 体验要素 #26 的真实落地。

### 2.1 命令规格

```
@TokenKnows /distill 2h
                     │
                     └─ 时间窗口 (OD-4 预设 5 选 1)

@TokenKnows /digest 7d           # 蒸馏 → weekly_report 类型
@TokenKnows /skill 30m           # 蒸馏 → agent_skill 类型 (走 Q5 同意流程)
@TokenKnows /distill today       # 蒸馏 → value_segments (无 asset, 仅入库)
```

**3 个 subcommand**：
- `/distill <window>`：仅入 ValueSegment，不生成 asset（最轻量；用户后续可手动选段生成）
- `/digest <window>`：→ 生成 `weekly_report` 类型 asset（适合周会前快速产周报）
- `/skill <window>`：→ 触发 Skill 蒸馏（需 contributor 同意，**§3 流程**）

### 2.2 触发流程

```
1. 用户在群里 @TokenKnows /digest 2h
2. IM connector 收到提及事件 (v0.3 已实现)
3. 新增 MentionDispatcher:
   a. 解析命令 + 校验语法
   b. 检查限频 (OD-3 每用户 5min 1 次)
   c. 拉群最近 2h 消息 (复用 v0.3 retention 内的消息)
   d. 过滤 redacted + 经 SignalGate (复用 v0.3 R1-R10 规则)
   e. 调 dispatcher (复用 v0.4 T30 完整管线)
4. dispatcher 直接 fire (跳过 5min 撤回窗口, 因为是用户主动触发)
5. asset 生成完成 (≈ 40s LLM pipeline)
6. 机器人在群里回 thread 消息: "[Demo] 已生成: https://tokenknows.../assets/:id"
```

### 2.3 数据模型

复用 `trigger_executions` 表，新增 mode 枚举值 `mention` + signal type `im_mention`：

```python
# schemas/auto_trigger.py 已有 TriggerMode = Literal['cron', 'event', 'threshold', 'mention']
# v0.5 让 mode='mention' 真正可用 (之前是预留)

# trigger_execution.signal:
{
  "type": "im_mention",
  "summary": "@TokenKnows /digest 2h · 后端技术群 · by alice",
  "payload": {
    "command": "digest",
    "window": "2h",
    "im_chat_id": "oc_xxx",
    "triggered_by_user_id": "ou_alice",
    "message_id": "om_xxx"
  }
}
```

**新增**：`im_mention_rate_limit` 内存计数（每群每用户 5min 滑动窗口）。

### 2.4 API

| 端点 | 备注 |
|---|---|
| POST `/api/v1/im/mentions/dispatch`（内部） | Webhook handler 调用；不对外暴露 |
| 复用 GET `/api/v1/projects/:pid/auto-triggers/executions?signal_type=im_mention` | UI 历史查询 |

---

## 3. 模块 B · Skill 蒸馏 Contributor 个人确认（Q5）

> v0.4.2 T42 自动 Skill 蒸馏的"补齐合规"。

### 3.1 状态机扩展

当前 `Skill.status: Literal['draft', 'active', 'deprecated', 'locked']`，**新增 2 个状态**：

```
distill_skill (自动 / @机器人触发, 且 contributor 同意书未签)
    ↓
status='pending_contributor_consent'  ← v0.5 新增
    ↓ (contributor 全员同意)
status='draft'  ← 与现有手动蒸馏一致
    ↓
... (后续 active / locked / deprecated 与 v0.2 一致)

任一 contributor 拒绝 → status='rejected_by_contributor'  ← v0.5 新增
30 天未响应 → status='expired_no_consent'
```

### 3.2 通知渠道

contributor 通知触发时机：skill 进入 `pending_contributor_consent` 时。

| 渠道 | 优先级 | 内容 |
| --- | --- | --- |
| IM DM（飞书/钉钉/企微） | 主 | "你最近的 X 条信号消息被识别为 K8s 专家技能, 是否同意发布 SKILL.md? \[同意\] \[拒绝\] [查看详情]" |
| Web 内 notification（铃铛角标） | 兜底 | 同上，但 link 跳 TokenKnows 网页详情 |

**实施**：
- 飞书 DM 用 `im/v1/messages` 端点（v0.3 已对接）
- 钉钉 / 企微 v0.3.1 J/K connector 同款方法
- web notification 走现有 SSE（auto_trigger.consent_request 新事件类型）

### 3.3 数据模型扩展

`Skill` Pydantic：

```python
class Skill(BaseModel):
    # ... 现有字段 ...
    status: Literal[
        'draft', 'active', 'deprecated', 'locked',
        # v0.5 新增:
        'pending_contributor_consent',
        'rejected_by_contributor',
        'expired_no_consent',
    ]
    # v0.5 新增 contributor 同意追踪
    consent_required_from: list[str] = Field(default_factory=list)
    """需要同意的 contributor user_id 列表 (从 Skill.contributors 派生)"""
    consent_signed_by: list[dict] = Field(default_factory=list)
    """已同意的 contributor: [{user_id, signed_at, channel: 'im_dm'|'web'}]"""
    consent_rejected_by: dict | None = None
    """首位拒绝的 contributor: {user_id, rejected_at, reason?, channel}"""
    consent_expires_at: datetime | None = None
    """OD-6: pending 后 +30 天; 超时 → expired_no_consent"""
```

**新表（可选）**：`skill_consent_history` —— 审计用，记录每次同意/拒绝的全量审计字段（IP / UA / 时间戳 / channel）。v0.5 第一波可跳过，写到现有 audit_log 表即可。

### 3.4 用户旅程（Alice 视角）

```
T+0:   Alice 在后端群里回答了 22 条 K8s 问题, SignalGate 标记为 signal
T+1d:  threshold_scanner 命中 "IM signal >= 20 → skill" 规则
       → T42 dispatcher 调 skill_service.distill_skill
       → Skill 草稿生成: name="kubernetes-troubleshooting-by-alice", contributors=[alice]
       → status='pending_contributor_consent'
       → 发 IM DM: "你最近的 22 条 K8s 信号被蒸馏为 SKILL.md, 是否同意发布?"
T+1d:  Alice 点 "查看详情" → 跳 TokenKnows /skills/:id 看完整 SKILL.md
       → 觉得 OK → 点 "同意"
       → status='draft' (与手动蒸馏一致, 进入审批流)
       → SSE 推 auto_trigger.consent_signed 事件
T+2d:  Owner 审批 draft → active → 后续生成自动注入
```

**拒绝场景：** Alice 觉得 SKILL.md 不准确 / 涉及敏感细节 → 点 "拒绝" → status=`rejected_by_contributor` → 30 天后归档；系统记录"此 contributor 在此主题上不愿被蒸馏"作为后续 SignalGate 训练负样本。

---

## 4. 技术架构

### 4.1 整体拓扑变化

```
v0.4 现有 + 红色为 v0.5 新增:

┌─────────────────────────────────────────────────────────────┐
│  IM Connector (v0.3)                                          │
│    Feishu/DingTalk/WeCom                                      │
│    ↓ 群消息流                                                  │
│    ↓ + 新增: 提取 @ 提及事件 ──→ MentionDispatcher (v0.5 新)  │
└────────────┬────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  Auto-Trigger Module (v0.4)                                  │
│    ┌─ cron_evaluator (T29)                                   │
│    ├─ event_evaluator (T40 GitHub webhook)                   │
│    ├─ threshold_evaluator (T41+T42)                          │
│    └─ MentionDispatcher (v0.5 新增) ← @ 触发即时 fire        │
│                                                              │
│    ↓ 命中后所有走 dispatcher.fire                             │
│                                                              │
│  dispatcher (T30):                                           │
│    ├─ asset_type ≠ agent_skill → start_generation (现有)     │
│    └─ asset_type == agent_skill →                            │
│       └─ Skill 蒸馏 + 检查 contributors                       │
│          └─ 有 contributors → status=pending_contributor (v0.5)│
│             └─ 触发 ConsentNotifier (v0.5 新增)              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 模块分解（v0.5 新增代码）

```
backend/app/services/auto_trigger/
├── mention_dispatcher.py    ← v0.5 新增
│   ├─ parse_command(text) → (subcommand, window) | error
│   ├─ check_rate_limit(chat_id, user_id) → bool
│   └─ dispatch_mention(chat_id, user_id, raw_msg) → trigger_execution

backend/app/services/skill/
├── consent.py               ← v0.5 新增
│   ├─ initialize_pending(skill) → 写 consent_required_from + consent_expires_at
│   ├─ sign_consent(skill_id, user_id, channel) → 更新 consent_signed_by
│   ├─ reject_consent(skill_id, user_id, reason?, channel) → 更新 consent_rejected_by
│   ├─ check_all_signed(skill) → bool (是否全员同意)
│   └─ sweep_expired() → 标 expired_no_consent (每天 03:00 调一次)

backend/app/services/im/
├── consent_notifier.py      ← v0.5 新增
│   ├─ notify_contributor(skill, user_id) → 发 IM DM + 写 web notification
│   ├─ Feishu/DingTalk/WeCom 三家 connector 各自实现 send_dm

backend/app/gateway/http_api/
├── skill.py                 ← v0.5 加 2 个端点
│   ├─ POST /skills/:id/consent/sign
│   └─ POST /skills/:id/consent/reject

frontend/src/features/skills/
├── ConsentPending.tsx       ← v0.5 新增 (skill 详情页 banner)
├── ConsentRequestNotification.tsx  ← v0.5 新增 (顶层铃铛)
```

### 4.3 与现有 dispatcher 衔接

`dispatcher.py` 第 ~55 行（_dispatch_skill_distill）已存在（T42），v0.5 在其内部加 2 行：

```python
async def _dispatch_skill_distill(execution, rule):
    # ... 现有 logic: 拉 top-20 signals, distill_skill ...
    skill = await skill_service.distill_skill(...)

    # v0.5 NEW: 如果有 contributors, 进入 pending_contributor_consent
    if skill.contributors:
        await skill_consent.initialize_pending(skill)  # 状态切 + 发通知
    return skill
```

### 4.4 部署形态

无新增容器/进程。`MentionDispatcher` 嵌入现有 IM connector 进程；`ConsentNotifier` 嵌入 FastAPI 主进程。

---

## 5. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- | --- |
| R1 | @ 机器人被恶意刷屏 | 中 | 中 | OD-3 限频 + 命令解析白名单 + audit_log |
| R2 | contributor 长期不回 → skill 堆积 | 中 | 低 | OD-6 30 天过期 → expired_no_consent 自动归档 |
| R3 | DM 通知失败（机器人被踢 / 用户禁言） | 中 | 中 | OD-7 兜底 web notification + 失败重试 2 次 |
| R4 | 多 contributor 同时拒绝 + 同意 → 状态机歧义 | 低 | 低 | OD-10 全员同意才 active；任一拒绝先到先得 → rejected |
| R5 | command 注入（用户构造特殊 command 触发非预期行为）| 低 | 高 | parse_command 严格 whitelist subcommand + window，其他全拒 |
| R6 | 拒绝后系统反复触发同主题 → 用户烦 | 中 | 中 | OD-9 拒绝信号入 SignalGate 负样本，30 天内同主题降权 |
| R7 | IM DM 跨企业边界（contributor 跳槽到其他公司）| 低 | 低 | DM 发送前 check IMConnection.status='active' |

---

## 6. 发布里程碑

### v0.5.0 · M5 @ 机器人按需触发（核心）
- MentionDispatcher 完整 (parse + rate limit + dispatch)
- 3 个 subcommand: distill / digest / skill
- IM 群内回执 (thread message)
- 复用 v0.3 IM 消息读取 + v0.4 dispatcher 管线
- 预计 1-1.5 sprint

### v0.5.1 · Contributor 个人确认
- Skill 状态机扩展 + consent tracking 表/字段
- ConsentNotifier (3 家 IM 各自 DM 发送)
- web 内 notification (铃铛)
- 2 个新 endpoint (sign / reject)
- 前端 ConsentPending banner + 顶层 notification
- daily sweep_expired
- 预计 1 sprint

### v0.5.2 · 真账单接入（小项）
- LLM Gateway / litellm 真 token usage → record_token_usage
- 替换 TOKEN_ESTIMATES_PER_TYPE
- 预计 0.5 sprint

> **Out of scope**：
> - PR file_glob 真支持（v0.5.3）
> - SSE 撤回通知（v0.5.4）
> - 多实例 scheduler（v0.6+）

---

## 7. 任务清单（v0.5.0 + v0.5.1）

| ID | 标题 | 类型 | 估算 |
|---|---|---|---|
| **T45** | 命令解析器 + 限频 + 数据模型 | backend | M |
| **T46** | MentionDispatcher + IM webhook 接入 | backend | M |
| **T47** | IM 群回执 (thread message) + 3 家 connector | backend | M |
| **T48** | Skill 状态机扩展 + consent tracking 字段 | backend | S |
| **T49** | ConsentNotifier (IM DM + web notification) | backend | M |
| **T50** | 2 个 sign/reject endpoints + sweep_expired | backend | S |
| **T51** | 前端 ConsentPending banner + notification | frontend | M |

总计 ~7 个 task / 估算 5-6 sprint（2 人月）。

---

## 8. 开放问题

| # | 问题 | 倾向 |
|---|---|---|
| Q1 | window 是否支持自定义时间（e.g. `/distill 3h`）？ | **否，仅 5 预设**（OD-4，安全）|
| Q2 | distill 不生成 asset 时 ValueSegment 怎么展示？ | 在工作台事件流加新类型 `im_segment_demo` |
| Q3 | 蒸馏成本是否计入 OD 触发者所在项目的 quota？ | **是**（与 cron/event 一致）|
| Q4 | contributor 同意后才发起 LLM 调用，还是先调 LLM 后求同意？ | **先调 LLM**（让 contributor 看到真实 SKILL.md 再决定；与 IM 同意书理念一致）|
| Q5 | M5 触发的 asset/skill 是否进 Reviewer 审批流？ | **进**（与 AT-5 一致, 不开后门）|

---

## 9. 变更日志

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.5-draft.1 | 2026-05-23 | 初稿，含 M5 + Q5 双模块 + 7 个任务 |

---

**Sources / 参考：**
- v0.4 Proposal §13.5 v0.5.4 @ 机器人按需蒸馏（v0.5 真实施）
- v0.4 Proposal §14 Q5 Skill 蒸馏 contributor 个人确认
- v0.3 IM Proposal §6.3 旅程 C · @ 机器人按需蒸馏（首次提出）
- v0.3 IM Proposal §7.4 IM-D 同意书（OD-6 / OD-7 设计源头）
