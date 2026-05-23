# T47 · IM 群内 Thread 回执 + 3 家 Connector

> v0.5.0 第三块。让机器人在原 thread 回执，保持群内对话透明。
> Proposal: [v0.5 OD-5 / §2.2 步骤 6](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
T46 dispatcher 生成 asset 后，机器人在原始 mention 消息的 thread 里回："[草稿] 已生成: <link>"。失败时降级到普通群消息（不阻塞流程）。

## 2. 范围
- **In**: 3 家 IM connector 各自的"在 thread 内回复"实现、统一抽象、失败兜底、`asset.id → public URL` 拼接
- **Out**: DM 通知（T49 ConsentNotifier 负责）

## 3. 三家 IM 的 thread 回复 API

| 平台 | API | thread 标识 |
|---|---|---|
| 飞书 | `POST im/v1/messages` body 含 `reply_in_thread: true` + `parent_id: <原 message_id>` | parent_id |
| 钉钉 | `POST robot/groupMessages/send` body 含 `openConversationId` + `originalMessageId`（thread 模式）| originalMessageId |
| 企微 | `POST cgi-bin/message/send`，不原生支持 thread，**降级为普通群消息**（quote 原文）| n/a |

## 4. 统一接口

```python
# app/services/im/thread_reply.py

class ThreadReplyError(Exception): ...

async def reply_in_thread(
    connection: IMConnection,
    chat_id: str,
    parent_message_id: str,
    text: str,
    link_url: str | None = None,
) -> str:  # 返回新发出消息的 id
    """根据 connection.platform 路由到对应 connector;
    企微回退到 send_to_chat (非 thread)."""
```

## 5. 消息模板

```
[Demo 草稿] 已生成 {asset_type_zh}
{title}

📄 {asset_url}
触发: @{user_login} /{subcommand} {window}
```

`asset_url` 由 `PUBLIC_BASE_URL` env + `/projects/{pid}/documents/{asset_id}` 拼接。

`{asset_type_zh}` 映射：weekly_report→周报 / adr→ADR / incident→复盘 / book→书籍 / agent_skill→Skill 草稿。

## 6. 组件分解

```
backend/app/services/im/
├── thread_reply.py              ← 统一入口
├── feishu_connector.py          ← 加 reply_in_thread() 方法
├── dingtalk_connector.py        ← 同上
├── wework_connector.py          ← 降级实现 (send_to_chat with quote)

backend/app/services/auto_trigger/
├── dispatcher.py                ← _dispatch_generation 成功后调 thread_reply
    (mention 类执行专属分支; 非 mention 不发回执)

backend/tests/test_thread_reply.py
backend/tests/test_dispatcher_mention_reply.py
```

## 7. 必备状态（DoD）
- [ ] 飞书 thread 回复成功
- [ ] 钉钉 thread 回复成功
- [ ] 企微降级到普通群消息成功（含原文 quote）
- [ ] thread_reply 失败 → dispatcher 不抛错，只 log 警告（asset 已生成不能回滚）
- [ ] `asset_url` 配置缺失（PUBLIC_BASE_URL 未设）→ 只发 asset title 不发链接

## 8. 验收
- [ ] 3 家平台真实 mention 后能看到 bot thread 回复
- [ ] 回复消息含正确 asset URL（点击能跳到 TokenKnows）
- [ ] 单测：每家 connector 的 reply 用 respx mock 上游 API，断言 payload 字段
- [ ] 集成测试：mention → dispatch → fire → thread_reply 全链路（mock LLM）

## 9. 已知陷阱
- 飞书 `parent_id` 必须是**同群内**的消息 ID，跨群无效
- 钉钉的 thread mode 在 robot vs 普通群应用之间 API 不同；优先用普通群应用接口
- 企微 `cgi-bin/message/send` 用 access_token (从 connection 解密)，与机器人 webhook URL 是两条路径
- bot 不在群里被发消息 → 401 / 404；catch + log，不阻塞 asset 生成
- 长消息（> 1024 字符）需要 truncate；用 `[..]` 截断 title 而非 URL
- 单元测试 mock 时三家的 status_code 都用 200 + 真实响应 schema（飞书返 message_id, 钉钉返 code:0）

## 10. Claude Code 指令
顺序：`thread_reply.py` 抽象接口 → 飞书实现（最完整）→ 钉钉 → 企微降级 → dispatcher mention 分支调用。每家写完后用真群跑一遍。错误处理不要重试（一次失败就 log 走人，asset 已经生成不能回滚）。
