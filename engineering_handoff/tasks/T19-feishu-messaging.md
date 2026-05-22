# T19 · 飞书消息读取（历史 + 实时）

## 1. 目标
完成 `FeishuConnector` 的消息能力：历史回填（默认 7 天）+ 实时 Webhook 订阅 + 归一化到 `IMNormalizedMessage`。
Proposal: §6.1 步骤 5-7 / §9.3 飞书适配器 / 附录 A.1

## 2. 范围
- **In**: list_chats / add_bot_to_chat / list_chat_members / fetch_history / stream_messages
- **Out**: SignalGate（T20）、ValueSegment 组装（T21）

## 3. 接口契约

| 方法 | 飞书 endpoint | 备注 |
|---|---|---|
| `list_chats` | `GET /open-apis/im/v1/chats` | 当前 user 可见的群 + 私聊 |
| `add_bot_to_chat` | `POST /open-apis/im/v1/chats/{chat_id}/members` | member_type=app, member_id=app_id |
| `list_chat_members` | `GET /open-apis/im/v1/chats/{chat_id}/members` | 用于归因映射 |
| `fetch_history` | `GET /open-apis/im/v1/messages` | params: container_id_type=chat, container_id, start_time, end_time, page_size=50, page_token |
| `stream_messages` | Webhook → Redis Pub/Sub → 异步消费 | 见下 |

## 4. Webhook 链路

```
飞书 → POST /api/webhooks/feishu/events/{tenant_key}
       (含 challenge / encrypted payload)
       ↓
   verify_signature() + decrypt(AES with FEISHU_ENCRYPT_KEY)
       ↓
   publish to redis channel `im:feishu:chat:{chat_id}`
       ↓
   stream_messages() 异步迭代器从 channel 取
```

事件类型：`im.message.receive_v1`（v0.3.0 只订阅这一个）。

## 5. 组件分解

```
backend/src/im/feishu/
├── messaging.py             ← list_chats / add_bot_to_chat / fetch_history
├── webhook.py               ← signature 校验 + AES 解密 + 入 redis
├── stream.py                ← redis subscribe → IMNormalizedMessage 生成器
└── normalizer.py            ← 飞书原始消息 → IMNormalizedMessage

backend/src/api/routes/
├── feishu_webhook.py        ← POST /api/webhooks/feishu/events/{tenant_key}
└── im_chats.py              ← GET /api/.../chats, POST /join, POST /leave

backend/src/workers/
└── im_backfill_worker.py    ← 异步消费 "回填请求"，调 fetch_history → 入库
                              ↑ 用户邀请 bot 入群时触发；窗口 = config.backfill_days（默认 7）

backend/tests/im/feishu/
├── test_messaging.py        ← respx mock
├── test_webhook.py          ← 验签 + 解密 round-trip
└── test_normalizer.py       ← 各 msg_type 归一化
```

## 6. 归一化要点

飞书消息 `body.content` 是 JSON 字符串，不同 msg_type 结构不同：

| msg_type | 提取 |
|---|---|
| `text` | `body.text` |
| `image` | `body.image_key` → 元数据，**不下载原图** |
| `file` | `body.file_name + file_key` |
| `audio` | duration + file_key；**v0.3.0 不做 ASR** |
| `interactive`（卡片） | `body` 整体当 content_meta，content_text 留空 |
| `system` | 标记 msg_type='system'，丢给 SignalGate 必判 noise |

## 7. 必备状态（DoD）
- [ ] Webhook 端点 5s 内必须返回 200（飞书超时会重试），重活推 redis
- [ ] 飞书 challenge 请求（首次配置）正确响应
- [ ] fetch_history 自动分页直到 has_more=false 或时间超过 start_time
- [ ] 重复消息幂等：UNIQUE (chat_id, platform_msg_id) 命中 → 不抛错、跳过
- [ ] 群 bot 已被踢出 → list/fetch 返回的 403/404 标记 chat.status='removed'

## 8. 验收
- [ ] 在测试群发消息，5s 内能在 redis channel 看到归一化后的消息
- [ ] fetch_history 拉 7 天数据 < 30s（群 ≤ 500 条/天）
- [ ] 7 种 msg_type 都能归一化、不抛异常
- [ ] Webhook 验签失败的请求返回 401，并记 audit_log
- [ ] 回填任务出错可重试，已入库的不重复

## 9. 已知陷阱
- 飞书事件订阅有两种：v1 加密、v2 不加密；本任务统一用 v1（更安全）
- Webhook 同步处理太久飞书会重发，导致消息重复；redis 入队后立即 200
- `page_token` 不是数字游标，是 opaque 字符串；不要尝试解析
- 私聊消息（chat_type=p1p）有更严格的权限要求，v0.3.0 默认不订阅，UI 隐藏选项
- mentions 数组里飞书给的是 `open_id`，归因到 internal_user 需要 T18 的 user mapping
- bot 入群成功是异步事件，前端要 poll chat 列表，不要假设入群立即生效

## 10. Claude Code 指令
顺序：normalizer.py（先纯函数好测）→ messaging.py → webhook.py（含签名/解密）→ stream.py → backfill worker。每写完一段就用真实飞书测试群跑一遍 happy path。
