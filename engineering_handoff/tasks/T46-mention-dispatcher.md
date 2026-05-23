# T46 · MentionDispatcher + IM Webhook 接入

> v0.5.0 第二块。把 T45 解析能力接到 IM 群消息事件 → 调用 v0.4 dispatcher 真生成 asset。
> Proposal: [v0.5 §2.2 触发流程 / §4.3](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
让 IM 群里 `@TokenKnows /digest 2h` 的提及消息能 30-60 秒内产出一份真 LLM 生成的 asset，UX 与 v0.4 cron/event/threshold 一致但**跳过 5 分钟撤回窗口**（用户主动触发，撤回无意义）。

## 2. 范围
- **In**: `dispatch_mention(chat_id, user_id, message_id, command_text)` 主流程、3 家 IM connector 的 @ 检测、消息流接入
- **Out**: 群内 thread 回执（T47）、命令解析本身（T45）

## 3. 触发流程

```
1. v0.3 IM connector 群消息事件 (im_message_received)
2. 检测是否含 @TokenKnows mention
   - 飞书: <at user_id="本应用 app_id"></at>
   - 钉钉: 文本含 @TokenKnows 或 atUsers 含 bot_user_id
   - 企微: msgtype=text 且 mentioned_list 含 bot
3. 抽 plain command text → T45 parse_command
4. 限频 check (T45)
5. 拉群 last <window> 消息 (复用 v0.3 list_im_messages + retention)
6. 过 SignalGate (复用 v0.3 R1-R10)
7. 构造 TriggerSignal(type='im_mention', payload=...)
8. 直接 svc.schedule_execution(rule_id_for_mention, project_id, signal, withdraw_window_min=0)
   ← 关键: window_min=0 → fire_at=now → withdraw_resolver 立即拉走
9. dispatcher.fire → start_generation → asset 入库
10. T47 在群里回 thread message: "[草稿] 已生成: <link>"
```

## 4. 项目映射

IM chat → TokenKnows project 关联（v0.3 已有 `im_connections.project_id` 字段）：
- 群 `chat_id` 查 `im_messages.connection_id` → `im_connections.project_id`
- 若该群未绑定项目 → mention 拒绝（机器人回 "本群未绑定 TokenKnows 项目"）

## 5. 触发"伪规则"

mention 触发不依赖现有 `trigger_rules` 表的某条规则，而是用一条**虚拟规则**：

```python
# 在 mention_dispatcher.py 内常量
MENTION_VIRTUAL_RULE = TriggerRule(
    id="rule-virtual-mention",
    project_id=None,
    name="@ 机器人按需触发",
    mode="mention",
    asset_type="<dynamic>",  # 由 command 决定
    enabled=True,
    cooldown_seconds=0,
    daily_cap=100,  # T45 限频已防刷
    ...
)
```

`asset_type` 由 subcommand 映射：
- `/distill` → `value_segments_only`（不生成 asset，仅入 ValueSegment；T46 内分支处理）
- `/digest` → `weekly_report`
- `/skill` → `agent_skill`（走 v0.4.2 T42 蒸馏 + v0.5.1 Q5 同意流程）

## 6. 组件分解

```
backend/app/services/auto_trigger/
├── mention_dispatcher.py
│   ├── (T45 已有 parse + rate_limit)
│   ├── extract_mention_text(im_message) → str | None  ← 3 家 connector 差异
│   ├── resolve_project_for_chat(chat_id) → project_id | None
│   ├── dispatch_mention(chat_id, user_id, msg) → trigger_execution
│   └── MENTION_VIRTUAL_RULE

backend/app/services/im/
├── feishu_connector.py     ← 加 _on_group_message_with_mention hook
├── dingtalk_connector.py   ← 同上
├── wework_connector.py     ← 同上

backend/tests/test_mention_dispatcher.py
backend/tests/test_im_mention_extraction.py  ← 3 家差异回归
```

## 7. 必备状态（DoD）
- [ ] 三家 IM connector 都能正确从原始消息中提取 mention 文本
- [ ] 未绑定项目的群提及 → 机器人回错误，不调 LLM
- [ ] 解析失败（命令文法错）→ 机器人回简短帮助，不调 LLM
- [ ] 限频拒绝 → 机器人回"5 分钟后再试"
- [ ] 完整 happy path：`@TokenKnows /digest 2h` → 30-60s 后群里有 thread 回执
- [ ] mention 触发的 trigger_execution.signal.type = `im_mention`

## 8. 验收
- [ ] 3 家 IM 各发 1 条真 mention 测试消息 → 都能进 dispatch
- [ ] 抓 backend log 看 schedule_execution 写入 withdraw_window_min=0
- [ ] dispatcher.fire 的 asset.trigger_meta.signal.type == 'im_mention'
- [ ] 单测覆盖率 ≥ 80%
- [ ] mention rate_limit 端到端测试（连续 2 次同用户）

## 9. 已知陷阱
- 飞书的 `<at>` 节点的 user_id 是 `open_id`（应用级），不是 `union_id`；区分 bot 与普通用户用 `app_id == 配置中的 FEISHU_APP_ID`
- 钉钉 `atUsers` 数组里 bot 的 `dingtalkId` 是配置的 `robotCode`（不是 user_id），别记错
- 企微的 mention 表达式有时是 `@TokenKnows&nbsp;`，HTML decode 后再 split
- IM webhook 的"群消息事件"和"私聊消息事件"是不同类型，本任务只在群消息里处理 mention；私聊 mention 留 v0.6+
- withdraw_window_min=0 时 `fire_at = now`，withdraw_resolver 下一秒就拉走；用户感知是"立即开始生成"
- 若 `/distill` 仅入 ValueSegment 不生成 asset，dispatcher 需要新分支；与 v0.4.2 T42 的 Skill 分支并列

## 10. Claude Code 指令
顺序：`resolve_project_for_chat`（纯 store 查询）→ `extract_mention_text` × 3 家 connector（写完每家单测）→ `dispatch_mention` 整合 → 接到 connector 的群消息 hook。最后跑 3 家真消息回归。
