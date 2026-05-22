# Proposal · TokenKnows v0.3 · 企业 IM 知识蒸馏

> 单独提案文档 — 把飞书 / 钉钉 / 企业微信作为新数据源，扩展 TokenKnows 的 Event → ValueSegment → Asset/Skill 蒸馏管线。

---

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | TokenKnows v0.3 · 企业 IM 知识蒸馏 产品技术方案 |
| 文档版本 | v0.3-impl.1 (主体已实施) |
| 文档状态 | ✅ T16-T25 + v0.3.1 P1+P2 完成 (commit dce310b); 待生产环境冒烟 |
| 撰写日期 | 2026-05-22 |
| 实施日期 | 2026-05-22 |
| 关联文档 | [PRD MVP](./PRD_TokenKnows_MVP.md) · [TDD MVP](./TDD_TokenKnows_MVP.md) · [BRD](./BRD_AI研发知识资产引擎.md) · [部署指南](./docs/V0.3_IM_DEPLOY.md) |
| 目标读者 | 产品、研发、合规、商务 |
| 体例 | PRD + TDD 一体，§3-§8 偏产品，§9-§14 偏技术 |

> **实施状态摘要** (2026-05-22 commit dce310b):
> - ✅ T16 DB schema (38 tests) — 3 表 + Fernet token 加密
> - ✅ T17 IMConnector ABC (13 tests) — 4 平台共享抽象
> - ✅ T18 飞书 OAuth (35 tests) — 4 方法 + callback handler
> - ✅ T19 飞书消息拉取 (20 tests) — list_chats / fetch_history 翻页
> - ✅ T20 SignalGate (15 tests) — R1-R10 规则 (R10 启发式, Qwen2.5-3B 留 v0.3.1)
> - ✅ T21 ValueSegment 组装 (15 tests) — 时间窗 + 话题切换
> - ✅ T22 Retention (15 tests) — 90 天清理 + 撤回宽限 + 匿名化
> - ✅ T23 REST API (20 tests) — 11 端点
> - ✅ T24 前端向导 (8 tests) + T25 群管理 (UI)
> - ✅ v0.3.1 P1 retention 后台 task (6 tests) — main.py 启动
> - ✅ v0.3.1 P2 Webhook 签名+解密 (28 tests) — 完整链路
>
> **总计 205 新测试 / 750 backend 全绿 / 5 个 commit (75dfbe4..dce310b)**
>
> **生产前 checklist 见 [V0.3_IM_DEPLOY.md](./docs/V0.3_IM_DEPLOY.md)**.

### 1.1 与 MVP 的关系

| 维度 | MVP（v0.1-v0.2） | 本提案（v0.3） |
| --- | --- | --- |
| 数据源 | Claude Code / Cursor / VS Code / GitHub | **+ 飞书 / 钉钉 / 企业微信** |
| 资产产出 | 周报 / 书籍长文 / Agent Skills | 同上，**新增"对话蒸馏专属"模板** |
| 部署形态 | 私有化优先 + SaaS 预留 | 同上，**会话内容必须私有化处理**（合规硬约束） |
| LLM 路由 | LLM Gateway 抽象层（PRD §6.6） | **复用**，无新增 |
| 数据脱敏 | D5 脱敏流水线（PRD §5.6） | **复用** + 新增 IM 专属规则（@ 提及、emoji 名、群名） |

### 1.2 关键决策表（v0.3）

| # | 决策 | 取值 | 备注 |
| --- | --- | --- | --- |
| IM-1 | 接入平台优先级 | **飞书 → 钉钉 → 企业微信** | 飞书 OpenAPI 最完整；企微会话存档涨价（2026-01-22 起 100% 涨幅）成本最高 |
| IM-2 | 数据模式 | **双轨**：A 个人助理模式 / B 企业会话存档模式 | A 合规阻力小、先上；B 价值大、需企业付费 |
| IM-3 | 个人微信 | **不支持** | 无官方 API；非官方协议封号风险高 |
| IM-4 | 接入触发 | **企业管理员授权 + 员工知情同意双签** | 《个人信息保护法》硬要求 |
| IM-5 | 数据驻留 | **会话原文不出本地**；蒸馏后的 ValueSegment 可出域（脱敏后） | 同 MVP §6.7 |
| IM-6 | 蒸馏触发 | **被动监听**（B 模式，订阅事件流） + **主动按需**（A/B 通用，@ 机器人） | 被动方式必须有员工同意 |
| IM-7 | 归因策略 | message_id → user_id → ValueSegment.contributors[] 全链路追踪 | 复用 MVP Evidence 模型 |
| IM-8 | 信号识别前置 | **必须有 SignalGate**（噪声过滤）才进入蒸馏管线 | 群聊噪声率经验值 ~70-85%，不过滤会拖垮成本 |
| IM-9 | 部署形态 | 会话存档代理（IMConnector）必须私有化部署 | 企业微信 C 版 SDK 强制要求 |
| IM-10 | LLM 路由 | 蒸馏走 LLM Gateway，企业可指定本地模型 | 复用 MVP §6.6 |
| IM-11 | v0.3.0 发布策略 | **5 家定向试点 30 天 → 反馈 → 小范围公测** | 2026-05-22 确认；校准 §15 附录 C 假设值的关键依赖 |
| IM-12 | 历史回填窗口 | **默认 7 天**，用户可手动调长 | 2026-05-22 确认；首次体验 <10min 出结果、API 限流压力低 |
| IM-13 | SignalGate 本地模型 | **Qwen2.5-3B（4-bit 量化）** | 2026-05-22 确认；中文最佳、CPU 可跑、Apache 2.0 可商用 |
| IM-14 | IM 原始消息保留期 | **默认 90 天**，到期自动清理；ValueSegment 不受此限 | 2026-05-22 确认；与 SOC2 / ISO27001 常见配置对齐 |

### 1.3 体验要素新增

延续 MVP 的 22 条体验要素编号（PRD §1.2），v0.3 新增：

| # | 要素 | 出现位置 |
| --- | --- | --- |
| 23 | IM 接入向导（飞书/钉钉/企微三选一） | §7.1 / §8.1 |
| 24 | 员工同意书"二次确认"弹层（首次启用必弹） | §7.2 / §8.4 |
| 25 | 噪声过滤可视化（dropped / kept 比例显示） | §8.2 |
| 26 | @ 机器人按需蒸馏（群里 @ 触发蒸馏指定时间段） | §7.3 / §8.1 |
| 27 | 贡献者归因卡（蒸馏出的 skill 显示 top-N 贡献者） | §8.5 |
| 28 | IM 数据保留期可配置（默认 90 天，到期自动清理） | §12.3 |

---

## 2. 关键约束（前置，决定方案形态）

在写任何模块之前，必须把三个硬约束钉死，否则方案不成立。

### 2.1 合规约束（最强约束）

**法律依据：**

- 《中华人民共和国个人信息保护法》（PIPL）第 13 条：处理员工通信数据必须有"取得个人单独同意"或"为订立、履行劳动合同所必需"
- 《数据安全法》第 27 条：重要数据出境必须安全评估
- 各家平台用户协议：飞书 / 钉钉 / 企业微信均明文要求 ISV 不得未经授权读取/留存会话内容

**对方案的强制要求：**

1. **必须有企业管理员授权**：通过各家 OpenAPI 的应用授权流程，由 IT 管理员代表企业法人授权 TokenKnows 应用
2. **必须有员工个人同意**：B 模式（会话存档）下，**每个**被监听员工必须签署知情同意书；不签的员工的消息必须被过滤掉（不能蒸馏、不能归因）
3. **同意书必须可撤回**：撤回后历史数据必须在 30 天内删除（与 PIPL 第 15 条对齐）
4. **必须有数据保留期**：默认 90 天，到期自动清理原始消息；蒸馏后的 ValueSegment 保留更长（脱敏后属于"派生数据"）
5. **必须有审计日志**：每次会话访问/蒸馏/导出都要落 audit_log，含操作人 + 时间 + 范围

### 2.2 信噪比约束

**经验值（行业公开数据估算）：**

| 场景 | 高信号比例 | 噪声主要构成 |
| --- | --- | --- |
| 技术 1-on-1 私聊 | 40-60% | 闲聊、表情、确认词 |
| 项目工作群 | 15-30% | 同上 + 公告、刷屏、@all |
| 部门大群 | 5-15% | 同上 + 福利、活动、无关 |
| 兴趣 / 闲聊群 | < 5% | 几乎全是噪声 |

**对方案的强制要求：**

1. **SignalGate** 必须在蒸馏管线之前：用规则 + 小模型（如 Qwen2.5-3B 或 LLM Gateway 的 cheap path）做前置二分类
2. SignalGate 决策必须可观测：每个 chat 显示 dropped / kept 比例（要素 #25）
3. SignalGate 阈值必须可调：默认 0.4（保守），管理员可调到 0.2（激进）或 0.6（节流）
4. 默认**只蒸馏工作群**，不蒸馏私聊（除非用户在 A 模式主动开启自己私聊的蒸馏）

### 2.3 归因约束

**问题：** 蒸馏出的 skill / 文档段落，知识产权归个人还是企业？

**v0.3 的处理（不解决，但显式标注）：**

1. **数据上**：每条 ValueSegment 保留 `contributors[]` 数组，记录哪些 user_id 提供了原始消息
2. **法律上**：在企业管理员授权时，必须同意"基于本企业 IM 数据蒸馏的产物归属本企业"——这是企业合同条款
3. **个人保护**：员工可在个人设置看到自己贡献过的 ValueSegment 列表，可申请"匿名化"（移除自己的 user_id 关联）
4. **撤回权**：员工撤回同意时，contributors[] 中自己的部分被打 anonymized=true 标记，但派生的 skill 不删除（防止恶意撤回销毁知识资产）

---

## 3. 产品概述

### 3.1 定位与价值

**一句话定位：** 让企业 IM 中流淌的"问答、决策、复盘"沉淀为可检索、可复用的知识资产，与 MVP 的 Claude Code / GitHub 数据源**形成闭环**——研发过程在哪里发生，TokenKnows 就到哪里。

**为什么 IM 是高价值数据源？**

1. **隐性知识密度高**：技术答疑、架构讨论、踩坑复盘 → 这些内容很少进文档，但全在群聊里
2. **决策上下文完整**：一个技术决定的来龙去脉（为什么这样做、否决了哪些方案）通常只在 IM 留痕
3. **专家可识别**：群里常发权威回复的人 = 团队隐性专家；通过归因可以让"专家技能"沉淀为 skill（与 MVP §5.8 Skill 自进化机制对接）
4. **时效性强**：IM 数据比 PR 提前 1-7 天反映团队当前讨论的焦点；做"上周技术热点"周报极有价值

**与现有工具的差异化：**

| 类型 | 代表产品 | 我们的差异 |
| --- | --- | --- |
| IM 平台自带的"会话搜索" | 飞书 / 钉钉 / 企微原生 | 它们只搜不蒸馏；我们做语义识别 + 资产化 |
| 客服会话分析 SaaS | 智齿 / 容联七陌 | 它们面向 To-C 客服，我们面向 To-B 研发知识 |
| 通用 IM 机器人 | Bot Framework | 它们是被动响应；我们是主动蒸馏 + 资产化 |
| MVP 已有 | TokenKnows v0.2 | v0.2 缺 IM 这一最关键的"过程数据"，v0.3 补齐 |

### 3.2 MVP 范围（v0.3.0 - v0.3.3 渐进交付）

| 版本 | 范围 | 预计周期 |
| --- | --- | --- |
| **v0.3.0** | 飞书"个人助理模式"：用户自己授权，只蒸馏自己发出/被 @ 的消息 | 2-3 sprint |
| v0.3.1 | 飞书企业会话存档模式：企业管理员开通，全员可选加入 | +2 sprint |
| v0.3.2 | 钉钉接入（A + B 双模式） | +2 sprint |
| v0.3.3 | 企业微信会话存档接入（C 版 SDK） | +2-3 sprint |
| v0.3.4 | 三家平台统一的"@ 机器人按需蒸馏"（要素 #26） | +1 sprint |

> **Out of scope（明确不做）：**
> - 个人微信（任何形态）
> - 海外 IM（Slack / Teams / Discord）—— 留 v0.4
> - 视频会议字幕蒸馏（飞书妙记除外，下一版考虑）
> - 邮件—— v0.5 单独提案

### 3.3 目标用户

| 角色 | 价值 | 阻力 | 切入点 |
| --- | --- | --- | --- |
| 研发负责人 | 让团队隐性知识不流失；技术决策可追溯 | 担心隐私问题、员工抵触 | "我们先在自己的 1 个项目群试 30 天" |
| IT/合规负责人 | 数据私有化、可审计 | 担心数据外泄、上级追责 | 同意书 + 审计日志 + 私有化部署"三件套"答疑 |
| 普通研发员工 | 自己写过的回答能复用、不用反复回答同一问题 | 担心被监控、被评估 | 个人助理模式（A）先用，体感安全后再考虑 B |
| 一线管理者 | 周报、月报自动生成、新人 onboarding 资料自动沉淀 | 担心质量不可控 | Reviewer 流程强保留（MVP §4.3） |

---

## 4. 平台能力矩阵

> 三家 IM 的 OpenAPI 能力差异巨大，决定了适配器实现的成本和合规路径。本节是技术决策的依据。

### 4.1 飞书 / Lark

| 维度 | 能力 |
| --- | --- |
| OpenAPI 完整度 | ★★★★★（最完整，覆盖 IM / 文档 / 多维表格 / 日历） |
| 历史消息拉取 | `im/v1/messages` (按 chat_id + 时间段)，受应用权限范围限制 |
| 实时事件订阅 | Event Subscription（Webhook 或 WebSocket）—— `im.message.receive_v1` 事件 |
| 接入应用类型 | 自建应用（企业内部）/ 商店应用（ISV 上架） |
| 权限申请 | 应用权限页申请 `im:message`、`im:chat:readonly`、`im:chat` 等 scope；商店应用需走平台审核 |
| 关键约束 | 应用必须被加入到群（机器人入群），才能读取该群消息；私聊只能读取与机器人的会话 |
| 个人助理模式可行性 | ✅ 可行：用户自己创建机器人，把机器人拉进自己的群 |
| 企业模式可行性 | ✅ 可行：企业自建应用 + 管理员开通"获取群消息"权限 + 强制全员入群 |
| 加密 | HTTPS + 应用密钥；事件回调可选 AES 加密（EncryptKey） |
| Python SDK | `oapi-sdk-python`（官方） |
| 官方文档 | [open.feishu.cn](https://open.feishu.cn/document/server-docs/im-v1/message/list) |

**对应方案：** 飞书是首发平台。个人助理模式（A）实现最快，2-3 sprint 可上线。

### 4.2 钉钉 / DingTalk

| 维度 | 能力 |
| --- | --- |
| OpenAPI 完整度 | ★★★★☆（IM 接口完整，但商业化授权较繁） |
| 历史消息拉取 | `/v1.0/im/sessions/messages` (按 open_conversation_id + 时间段) |
| 实时事件订阅 | Stream 模式（长连接） / HTTP 回调；事件 `IMReceiveMessage` |
| 接入应用类型 | 企业内部应用 / ISV 应用 / 第三方企业应用 |
| 权限申请 | "Card.Streaming.Write"、"Chat.Message.Get" 等粒度权限，需企业管理员审批 |
| 关键约束 | 与飞书类似，机器人入群才能监听；ISV 应用需要走"开发者后台"审核 |
| 个人助理模式可行性 | ✅ 可行 |
| 企业模式可行性 | ✅ 可行；钉钉 4.0 新增"会话存档"也是付费功能（与企业微信类似） |
| 加密 | HTTPS + SuiteSecret；回调 AES + token 签名 |
| 主流 SDK | `dingtalk-stream`（官方 Python/Node） |
| 官方文档 | [open.dingtalk.com](https://open.dingtalk.com/document/) |

**对应方案：** 第二个接入。SDK 与飞书可抽象为同一个 IMConnector 接口。

### 4.3 企业微信 / WeCom

| 维度 | 能力 |
| --- | --- |
| OpenAPI 完整度 | ★★★☆☆（IM 部分相对受限，但有专门的"会话内容存档"产品） |
| 历史消息拉取 | **没有通用接口**，必须走"会话内容存档"付费产品 |
| 实时事件订阅 | 群消息事件（机器人模式有限），完整监听必须用会话存档 SDK |
| 接入应用类型 | 企业内部应用 / 第三方应用 / 代开发应用 |
| 会话存档 | **C 版 SDK（WeWorkFinanceSDK）**，本地部署、本地解密 |
| 会话存档价格 | **办公版 400 元/人/年、服务版 900 元/人/年、企业版 1800 元/人/年**（2026-01-22 起，价格 100% 上涨） |
| 个人助理模式可行性 | ⚠️ 受限：企业微信对个人开发者不友好，必须企业主体认证 |
| 企业模式可行性 | ✅ 可行，且这是企业微信**唯一**合规的会话读取路径 |
| 加密 | RSA 公钥下发、企业本地存私钥；C SDK 调用 `GetChatData` 拉密文，`DecryptData` 解密 |
| 主流 SDK | 官方 C 库 + 社区 Go/Node/Java 封装（[NICEXAI/WeWorkFinanceSDK](https://github.com/NICEXAI/WeWorkFinanceSDK) 等） |
| 官方文档 | [developer.work.weixin.qq.com](https://developer.work.weixin.qq.com/document/path/91774) |

**对应方案：** 最后接入。成本最高（人头费 + C SDK 集成复杂度），但金融/政企客户高频需求。

### 4.4 平台对比汇总

| 平台 | 个人模式难度 | 企业模式难度 | 企业模式额外成本 | v0.3 优先级 |
| --- | --- | --- | --- | --- |
| 飞书 | 低（2-3 sprint） | 中（2 sprint） | 0（OpenAPI 免费） | P0 |
| 钉钉 | 低 | 中 | 0（OpenAPI 免费） | P1 |
| 企业微信 | 高 | 高（C SDK + RSA） | **400-1800 元/人/年** | P2 |

---

## 5. 双轨数据模式

### 5.1 模式 A · 个人助理模式

**定义：** 用户在自己的 IM 账号上启用 TokenKnows 机器人，机器人只能读到**该用户自己发出 / 自己被 @ / 自己加入的群**里的消息。

**数据归属：** 个人。蒸馏出的 skill 默认归该用户所有，可选共享到团队。

**合规路径：**
- 飞书：用户自己创建"个人机器人"或安装 TokenKnows 商店应用到自己账号；不需要企业管理员授权
- 钉钉：类似
- 企业微信：**不支持**（企业微信不允许个人级应用）

**典型场景：**
- 个人研发：把自己回答过的技术问题沉淀为个人 skill 库
- 自由职业者 / 顾问：把客户对话蒸馏为方法论
- 新人 onboarding：把自己学习过程的问答沉淀

**优势：**
- 合规阻力最小，**不需要企业法务介入**
- 数据归属清晰
- 上线速度快（飞书 2-3 sprint）

**限制：**
- 数据量小（一个人的对话比一个团队少 1-2 个数量级）
- 难以蒸馏"团队共识"类知识

### 5.2 模式 B · 企业会话存档模式

**定义：** 企业 IT 管理员开通 TokenKnows 企业应用，全员或选定人员的 IM 会话（白名单群）被持续拉取/订阅，进入企业知识库。

**数据归属：** 企业。

**合规路径：**
- 飞书：企业自建应用 + `im:message` 权限 + 机器人入群
- 钉钉：第三方企业应用 + `Chat.Message.Get` + 入群
- 企业微信：**必须**走会话存档 C SDK + 付费

**典型场景：**
- 团队工作群、技术支持群的全量蒸馏
- 跨项目沉淀团队最佳实践
- 高频专家问答自动建索引（"找谁问 K8s" → 自动推荐）

**优势：**
- 数据量大、覆盖全
- 能蒸馏团队共识 / 隐性专家
- 企业付费意愿高（关键决策依据）

**限制：**
- 合规复杂：员工同意书 + 审计 + 私有化部署
- 企业微信场景下成本高（**最低 400 元/人/年**仅含会话存档功能费，不含 TokenKnows）
- 实施周期长（合规审查 + IT 部署 4-8 周）

### 5.3 双轨共存策略

**v0.3.0**：只做飞书 A 模式（最小可行）
**v0.3.1+**：A、B 并存，用户可在同一项目里同时使用

**关键设计：**
- 一个 TokenKnows project 可以挂接多个 IMConnection（含混合 A/B 模式）
- ValueSegment 上明确标注 `source_mode: 'personal' | 'enterprise'`
- 个人贡献的 ValueSegment 在切换雇主后默认**不带走**（除非用户在导出时勾选）

---

## 6. 核心用户旅程

### 6.1 旅程 A · 个人接入飞书（v0.3.0）

> 阿强是 Acme 公司后端组的研发，在飞书的"后端技术交流群"里经常回答 K8s 问题。他想把自己的回答沉淀为 skill。

```
1. 阿强在 TokenKnows 工作台 → 数据源 → 点 "+ 添加 IM"
2. 选 "飞书 · 个人助理模式" → 阅读合规说明 → 点 "继续"
3. 跳转飞书 OAuth 授权页 → 阿强用自己飞书账号登录 → 同意以下权限：
   - 读取自己发送的消息
   - 读取 @ 自己的消息
   - 读取自己所在群的消息（仅 TokenKnows 机器人入群后生效）
4. 回跳 TokenKnows → 显示 "授权成功，请选择要监听的群"
5. 阿强勾选 "后端技术交流群"、"K8s 学习小组" → 点 "邀请机器人入群"
6. 飞书弹窗确认 → 机器人入群成功
7. TokenKnows 后端开始拉取历史消息（默认最近 7 天）+ 订阅新消息
8. 24 小时后，SignalGate 过滤 + 蒸馏 → 阿强在 "Skills" 页看到 3 个 draft skill:
   - "K8s Pod 卡在 Pending 状态的 5 步排查法"
   - "Helm 多环境 values 文件组织规范"
   - "kubectl 调试 CrashLoopBackOff 的标准动作"
9. 阿强点开第一个 → 看到证据链：原始消息列表（自己的 5 条群聊回复）+ 时间 + 群名
10. 阿强觉得质量 OK，点 "发布" → skill 进入 active 状态，可被注入到后续生成
```

**关键交互点（要素映射）：**
- 步骤 2-3：合规说明 + OAuth → 要素 #24
- 步骤 5：机器人入群提示 → 要素 #4（数据源向导）
- 步骤 8：SignalGate 可视化 → 要素 #25
- 步骤 9：证据链 → 要素 #9（沿用 MVP §4.2）

### 6.2 旅程 B · 企业开通钉钉会话存档（v0.3.2）

> Acme 公司 CIO 决定全公司部署 TokenKnows，希望蒸馏所有技术群的隐性知识。

```
阶段 1：合规与采购（1-2 周）
1. CIO 联系 TokenKnows 商务 → 评估、报价、签合同
2. TokenKnows 提供：员工同意书模板（中英）+ 数据处理协议（DPA）+ 私有化部署清单
3. Acme 法务、HR 审核 → 全员发送同意书（OA 流程） → 收齐签字（90%+ 签字率视为可启用）

阶段 2：IT 部署（1 周）
4. Acme IT 部门把 TokenKnows 核心服务部署到内网（Docker Compose 简易版）
5. 在钉钉开发者后台创建第三方企业应用，权限：Chat.Message.Get + 通讯录只读
6. 把应用安装到 Acme 企业，授权管理员代企业签订同意书
7. 配置 TokenKnows 后端的钉钉适配器（应用 ID + Secret + Webhook URL）

阶段 3：白名单与启用（持续）
8. CIO 在 TokenKnows 管理后台 → IM 接入 → 钉钉 → 启用
9. 选择监听范围：
   - 群白名单：勾选 "技术-后端、技术-前端、技术-DevOps、产品-需求评审" 4 个群
   - 人员白名单：自动同步同意书签字员工列表（未签字员工的消息会被丢弃）
10. 启用 → 钉钉 Stream 长连接建立 → 实时事件流入 TokenKnows

阶段 4：使用（持续）
11. 一线员工在 TokenKnows 工作台看到 "IM 数据源"，可点开任一会话查看蒸馏出的 ValueSegment
12. 管理者定期看 "本周高价值蒸馏内容" 报告
13. Skill 自进化机制（MVP §5.8）开始基于 IM 数据迭代
```

**关键交互点：**
- 阶段 1 全程：合规文档化、可审计
- 阶段 3 步骤 9：人员/群双白名单 → 是核心合规闸门
- 阶段 4：与 MVP 工作台同入口，无新增 UI 心智负担

### 6.3 旅程 C · @ 机器人按需蒸馏（v0.3.4）

> 张三在群里看到一段精彩讨论，想立即蒸馏。

```
1. 张三在群里 @TokenKnows 机器人 → 输入 "/distill 最近 2 小时"
2. 机器人回复 "已收到，正在分析最近 2h 的 56 条消息..."
3. TokenKnows 拉取指定时间段消息 → SignalGate → 蒸馏 → 生成 1 个 ValueSegment 草稿
4. 机器人回复 "已生成草稿：[K8s 网络故障 5 步排查]，点击查看 → https://..."
5. 张三点链接 → 在 TokenKnows 编辑后发布 → 自动归属到当前项目
```

**关键设计：**
- 主动按需 = 不需要持续监听，**适合更敏感的群**（不愿全量存档但偶尔有金句）
- 时间窗口可选：30 分钟 / 2 小时 / 当天
- 触发者 = 蒸馏发起人，记入 audit_log

---

## 7. 功能需求

### 7.1 模块 IM-A · IM 连接器

> **目标**：用户能添加飞书 / 钉钉 / 企业微信连接，建立持续/按需的数据通道。

#### IM-A.1 连接器列表与创建

**位置：** TokenKnows → 项目 → 数据源 → IM Tab

**UI 状态卡片（每个连接器）：**

| 字段 | 示例 |
| --- | --- |
| 平台 | 飞书 |
| 模式 | 个人助理 / 企业会话存档 |
| 状态 | 未授权 / 已授权 / 同步中 / 已暂停 / 出错 |
| 监听范围 | 群 3 个 / 用户 12 人 |
| 数据量（30 天） | 消息 4.2k / 蒸馏 ValueSegment 38 |
| 最近同步 | 2 分钟前 |

#### IM-A.2 接入向导（Acceptance Criteria · Gherkin）

```gherkin
功能: 飞书个人助理模式接入

场景: 用户首次接入飞书
  Given 用户在 TokenKnows 项目工作台
  When 用户点击 "+ 添加 IM" → 选 "飞书 · 个人助理模式"
  Then 显示三个合规说明卡片:
    - "我们只读取你授权范围内的消息"
    - "原始消息不出本地（除非你启用云端 LLM）"
    - "你可以随时撤回授权，30 天内清理数据"
  And 显示 "继续" 按钮

场景: 用户完成 OAuth
  Given 用户已点击 "继续"
  When 跳转到飞书 OAuth 授权页 → 用户登录 → 同意权限
  Then TokenKnows 后端收到 authorization_code → 换取 access_token + refresh_token
  And 在数据库创建 IMConnection 记录 (mode=personal, platform=feishu, status=authorized)
  And 跳回前端 "选择群" 页

场景: 用户邀请机器人入群
  Given 用户在 "选择群" 页
  When 用户勾选 N 个群 → 点 "邀请机器人入群"
  Then 调用 feishu im/v1/chats/{chat_id}/members → 把 TokenKnows bot 加入这些群
  And 对每个成功入群的群，创建 IMChat 记录 (status=active)
  And 启动历史消息回填任务（默认拉最近 7 天）

场景: 历史消息回填完成
  Given 历史消息回填任务运行中
  When 任务完成
  Then 前端推送通知 "回填完成: N 条消息, 信号率 X%, 已生成 K 个 ValueSegment"
  And 显示前往 "Skills" 页的快捷链接
```

#### IM-A.3 用户操作

| 操作 | 行为 |
| --- | --- |
| 暂停同步 | 停止订阅事件 + 暂停历史回填；已有数据保留 |
| 恢复同步 | 重新订阅 + 增量拉取暂停期间的消息（仅 7 天内） |
| 移除群 | 把 bot 踢出群 + 该群的 IMChat status=removed；可选择是否删除该群的历史消息 |
| 撤回授权 | 调用平台 revoke API + 30 天内删除该 IMConnection 的所有原始消息 |

### 7.2 模块 IM-B · 信号识别（SignalGate）

> **目标**：在蒸馏之前过滤噪声，保证投入 LLM 的内容是高信号。

#### IM-B.1 SignalGate 二分类决策

**输入：** 一条消息（含上下文：前 5 条 + 后 2 条）
**输出：** `{ is_signal: bool, score: 0-1, reason: string }`

**判定规则（按优先级）：**

| 规则 | 判定 | 示例 |
| --- | --- | --- |
| R1 长度 < 5 字符 | noise | "嗯"、"好的"、"👍" |
| R2 全表情或全标点 | noise | "😂😂😂"、"???" |
| R3 系统消息 | noise | "X 加入了群聊"、"X 撤回了消息" |
| R4 转发 / 引用为主 | noise（除非有 ≥30 字原创补充） | 转发新闻、纯链接 |
| R5 问句 + 后续无回答 | weak（保留但低权重） | "K8s 用啥版本？" 然后无人答 |
| R6 问答配对（疑问句 + 5+ 字回答） | **signal** | Q: 为什么 Pod Pending? A: 多半是 nodeSelector 没配 |
| R7 决策表述（"我们决定"、"最终方案"、"达成共识"） | **signal** | "评审完了，我们决定用 Postgres" |
| R8 复盘 / 总结 | **signal** | "今天踩坑：xxx" |
| R9 链接 + 长描述 | maybe | 链接 + 50 字解读 → signal |
| R10 默认 | LLM 小模型分类（cheap path） | Qwen2.5-3B 给 0-1 分数 |

**决策合成：**
```
score = max(rule_score, llm_score) with rule weights:
  if R1-R4 命中 → score = 0 (强制 noise)
  elif R6-R8 命中 → score = max(0.7, llm_score) (强制 signal)
  else → score = llm_score
is_signal = score >= threshold (默认 0.4)
```

#### IM-B.2 ValueSegment 组装

SignalGate 是逐条判定，但 ValueSegment 是**段**级别（多条消息组成一段）。

**组装规则：**

1. 时间窗口聚合：相邻 signal 消息间隔 < 10 分钟 → 同一段
2. 话题切换检测：用 LLM 小模型判断"是否换了话题"，换了 → 切段
3. 段最小长度：< 50 字符的段丢弃
4. 段最大长度：> 2000 字符的段切分（避免 LLM context 浪费）

#### IM-B.3 可观测性（要素 #25）

每个 IMChat 显示：
- 7 天 / 30 天 / 全部时间窗口
- 总消息数 / signal 数 / noise 数 / 组成的 ValueSegment 数
- TOP-5 高频 contributor

#### IM-B.4 阈值调节

管理员可在项目设置调 SignalGate threshold：

| 档位 | threshold | 适用 |
| --- | --- | --- |
| 激进 | 0.2 | 安静的小群、价值密度高 |
| 默认 | 0.4 | 一般工作群 |
| 节流 | 0.6 | 噪声大、想省 LLM 成本 |

### 7.3 模块 IM-C · 蒸馏管线

> **目标**：把 ValueSegment 提升为 Asset（文档段落）或 Skill（专家技能）。

#### IM-C.1 与现有蒸馏管线的衔接

```
现有（MVP）:
  Event (PR/conversation) → ValueSegment → Asset Chapter (PRD §7.2)

v0.3 新增:
  IMMessage[] → SignalGate → IMValueSegment → 与 Event 同等地位 → 蒸馏管线
```

`IMValueSegment` **不是新表**，而是 ValueSegment 的一个变种，通过 `source_type='im'` 字段区分。

#### IM-C.2 触发模式

| 模式 | 触发 | 频率 |
| --- | --- | --- |
| 实时被动 | 每 30 分钟批量处理新 IMValueSegment（仅 B 模式） | 持续 |
| 阈值触发 | 累积 ≥ 10 个 IMValueSegment 触发蒸馏 | 自动 |
| 主动按需 | 用户在群里 @ 机器人 / 在工作台点 "蒸馏 IM" | 即时 |
| 定期 | 每周一上午自动蒸馏上周累积 | 周报场景 |

#### IM-C.3 产出类型

| 产出 | 适用 IM 数据特征 | 模板 |
| --- | --- | --- |
| 周报 / 月报章节 | 高频时事讨论 | 复用 MVP C1 |
| FAQ 文档 | 问答对密集 | 新模板：群问答精选 |
| 决策日志 | 含 R7（决策表述）的 ValueSegment | 新模板：技术决策记录 |
| 复盘报告 | 含 R8（复盘）的 ValueSegment | 复用 MVP C1 + 新增"事件时间线"段 |
| Agent Skill | 同一个 user_id 在同一主题反复提供高质量回答 | 复用 MVP §5.8 / C6 |

#### IM-C.4 蒸馏 AC

```gherkin
功能: IM 数据触发 skill 蒸馏

场景: 系统检测到隐性专家
  Given 用户 user_X 在最近 30 天里
    - 在 IMChat=ch_K8s 群里发了 20+ 条 signal 消息
    - 这些消息覆盖至少 3 个不同子话题（K8s 网络/存储/调度）
  When 每周自动检测任务运行
  Then 生成草稿 skill "K8s 故障排查 by user_X"
    - skill.contributors = [user_X]
    - skill.source_segments = [seg_id_1, seg_id_2, ...]
    - skill.status = draft
  And 在 user_X 的工作台显示通知 "系统从你的 IM 对话中蒸馏出 1 个 skill, 是否发布?"
  And user_X 拒绝 → skill.status=rejected; 接受 → status=active

场景: 蒸馏出的 skill 触发同意书校验
  Given 草稿 skill 的 contributors 包含 user_Y
  When 系统准备发布
  Then 校验 user_Y 的 IMConsent.status = 'agreed'
  And 若未同意 → skill 不发布, 在管理后台显示 "等待 user_Y 同意"
  And user_Y 个人页可看到 "你的对话被蒸馏出 1 个 skill, 是否同意发布?"
```

### 7.4 模块 IM-D · 归因与同意

> **目标**：每条蒸馏内容能追溯到具体消息和具体人；员工有撤回权。

#### IM-D.1 归因链路

```
Asset.Chapter.Evidence  (MVP §7.2)
  ↓
  Evidence.source_type = 'im'
  Evidence.source_id = im_message.id
  ↓
IMMessage.user_id = user_X
  ↓
IMConsent (user_X, project_id) → 必须存在且 status='agreed'
```

#### IM-D.2 同意书生命周期

| 状态 | 含义 | 转换条件 |
| --- | --- | --- |
| `pending` | 已发送，未签 | 默认 |
| `agreed` | 已同意 | 用户签字 |
| `declined` | 拒绝 | 用户拒签 |
| `revoked` | 撤回（曾同意） | 用户主动撤回 |
| `expired` | 过期 | 签字超过 1 年自动过期，需重签 |

**撤回行为：**
- 已蒸馏的 ValueSegment 的 contributors[] 中该用户被标记 `anonymized=true`（不再显示用户名）
- 已发布的 skill **不删除**，但 contributors 列表去除该用户
- 该用户的原始消息在 30 天内清理
- 撤回后再次同意 → 重新计入归因（但已脱落的不补）

#### IM-D.3 同意书模板（附录 B 给完整版）

关键条款：
1. 处理范围：哪些群、哪些时间段
2. 处理目的：蒸馏知识资产、不用于个人评估
3. 处理者：TokenKnows + 部署 TokenKnows 的本企业
4. 数据保留期：默认 90 天原始，蒸馏后无限期（除非撤回）
5. 撤回方式：在 TokenKnows 个人设置 → 撤回；或通过企业 HR
6. 不参与的后果：仅"该员工的消息不被蒸馏"，无其他不利后果（**这条很关键，证明非强制**）

### 7.5 模块 IM-E · 知识消费

> **目标**：让用户能找到、用上、复用 IM 蒸馏出的知识。

#### IM-E.1 在已有页面的延伸

| 页面（MVP 已有） | v0.3 新增内容 |
| --- | --- |
| 项目工作台事件流 | 新增 IM Message 事件类型（聚合显示，不一条一条刷屏） |
| Skills 页 | 新增筛选项 "数据来源" → IM / Code / GitHub / 全部 |
| 证据链查看 | 支持点 IM message 跳转到原始消息（飞书/钉钉 deeplink） |
| Document 编辑 | 段落级 "找证据" 按钮可搜索 IM 历史 |

#### IM-E.2 新增页面

**贡献者归因卡（要素 #27）：**

每个 skill 详情页底部新增：
```
Top Contributors:
  - 阿强 (12 messages, 7 segments)
  - 小明 (8 messages, 4 segments)
  - 张三 (3 messages, 1 segment)
```

**IM 数据健康度仪表板（管理员）：**

| 指标 | 示例 |
| --- | --- |
| 监听群数 | 8 |
| 监听人数 | 124 / 142 同意 |
| 30 天消息量 | 48,231 |
| Signal 率 | 18.4% |
| 30 天产出 | ValueSegment 1,238 / Skill 4 / Asset 23 |
| 平均蒸馏延迟 | 4.2 分钟 |
| 撤回事件 | 2 起（已合规处理） |

---

## 8. 数据模型

> 复用 MVP 的 user / project / asset / evidence 表，新增 5 张 IM 专属表。

### 8.1 IMConnection（IM 连接）

```sql
CREATE TABLE im_connection (
  id            UUID PRIMARY KEY,
  project_id    UUID NOT NULL REFERENCES project(id),
  user_id       UUID NOT NULL REFERENCES "user"(id),  -- 创建者
  platform      TEXT NOT NULL,  -- 'feishu' | 'dingtalk' | 'wecom'
  mode          TEXT NOT NULL,  -- 'personal' | 'enterprise'
  status        TEXT NOT NULL,  -- 'authorized' | 'syncing' | 'paused' | 'error' | 'revoked'
  -- OAuth / SDK 凭据 (加密存储)
  access_token_enc       BYTEA,
  refresh_token_enc      BYTEA,
  token_expires_at       TIMESTAMPTZ,
  -- 企业微信专属
  wecom_corp_id          TEXT,
  wecom_msgaudit_secret_enc BYTEA,
  wecom_private_key_enc  BYTEA,  -- RSA 私钥, 用于解密 chat_data
  wecom_private_key_version INT,
  -- 元数据
  display_name  TEXT,
  scopes        TEXT[],
  config        JSONB,  -- 平台特定配置: SignalGate threshold 等
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at    TIMESTAMPTZ,
  UNIQUE (project_id, platform, user_id, mode)
);
CREATE INDEX im_connection_status_idx ON im_connection(status) WHERE status NOT IN ('revoked');
```

### 8.2 IMChat（会话）

```sql
CREATE TABLE im_chat (
  id            UUID PRIMARY KEY,
  connection_id UUID NOT NULL REFERENCES im_connection(id),
  -- 平台原生 ID
  platform_chat_id TEXT NOT NULL,  -- feishu: oc_xxx, dingtalk: openConversationId, wecom: roomid
  chat_type     TEXT NOT NULL,  -- 'p2p' | 'group' | 'external_group'
  display_name  TEXT,
  member_count  INT,
  -- 监听控制
  status        TEXT NOT NULL,  -- 'active' | 'paused' | 'removed'
  added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  removed_at    TIMESTAMPTZ,
  -- 缓存
  last_synced_at         TIMESTAMPTZ,
  last_message_at        TIMESTAMPTZ,
  message_count_30d      INT DEFAULT 0,
  signal_rate_30d        REAL,
  -- 元数据
  metadata      JSONB,
  UNIQUE (connection_id, platform_chat_id)
);
CREATE INDEX im_chat_status_idx ON im_chat(connection_id, status);
```

### 8.3 IMMessage（消息原文，受保留期限制）

```sql
CREATE TABLE im_message (
  id                UUID PRIMARY KEY,
  chat_id           UUID NOT NULL REFERENCES im_chat(id),
  platform_msg_id   TEXT NOT NULL,
  -- 发送者
  sender_user_id    TEXT NOT NULL,  -- 平台原生 user_id (open_id / unionid / userid)
  sender_internal_id UUID,           -- 映射到 TokenKnows user 表（如果是企业用户）
  sender_name       TEXT,
  -- 内容
  msg_type          TEXT NOT NULL,  -- 'text' | 'image' | 'file' | 'voice' | 'card' | 'system'
  content_text      TEXT,           -- 文本内容（图片/语音不存原始，仅存元数据和 transcript 如有）
  content_meta      JSONB,          -- 富媒体元数据: file_name, image_url, voice_duration 等
  mentions          TEXT[],         -- @ 提到的人 (平台 user_id 列表)
  reply_to_msg_id   TEXT,           -- 引用回复
  -- 时间
  sent_at           TIMESTAMPTZ NOT NULL,
  received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- SignalGate 结果
  signal_score      REAL,
  signal_reason     TEXT,
  is_signal         BOOLEAN,
  -- 合规
  redacted          BOOLEAN DEFAULT false,
  retention_until   TIMESTAMPTZ NOT NULL,  -- 默认 90 天后自动清理
  -- 索引
  UNIQUE (chat_id, platform_msg_id)
);
-- 分区: 按 received_at 月分区（与 MVP TDD §5.5 对齐）
CREATE INDEX im_msg_sent_at_idx ON im_message(chat_id, sent_at DESC);
CREATE INDEX im_msg_signal_idx ON im_message(chat_id, is_signal, sent_at DESC) WHERE is_signal = true;
CREATE INDEX im_msg_retention_idx ON im_message(retention_until) WHERE redacted = false;
```

**冷热分层（沿用 MVP TDD §5.5）：**
- 7 天内：热存储（Postgres）
- 7-90 天：温存储（同 Postgres，但只允许批查询）
- 90 天后：到期前 7 天发通知；到期自动 DELETE（除非用户延期）

### 8.4 IMConsent（员工同意书）

```sql
CREATE TABLE im_consent (
  id                UUID PRIMARY KEY,
  project_id        UUID NOT NULL REFERENCES project(id),
  -- 员工身份
  platform          TEXT NOT NULL,
  platform_user_id  TEXT NOT NULL,  -- 平台原生 user_id
  internal_user_id  UUID,            -- 映射到 TokenKnows user（如果是用户）
  display_name      TEXT,
  email             TEXT,
  -- 同意状态
  status            TEXT NOT NULL,  -- 'pending' | 'agreed' | 'declined' | 'revoked' | 'expired'
  consent_text_version TEXT NOT NULL,  -- 同意书版本（变更需重签）
  -- 时间线
  sent_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  signed_at         TIMESTAMPTZ,
  revoked_at        TIMESTAMPTZ,
  expires_at        TIMESTAMPTZ,  -- 默认 signed_at + 1 year
  -- 签名证据
  signature_method  TEXT,  -- 'oauth_click' | 'email_link' | 'oa_form'
  signature_meta    JSONB,  -- IP / UA / 时间戳等
  UNIQUE (project_id, platform, platform_user_id)
);
CREATE INDEX im_consent_status_idx ON im_consent(project_id, status);
```

### 8.5 IMAttribution（归因记录，扩展 ValueSegment）

不新建表，而是在 ValueSegment / Skill 表上加字段（沿用 MVP §7.2）：

```sql
-- ValueSegment 表新增字段（patch）
ALTER TABLE value_segment ADD COLUMN source_type TEXT;  -- 'event' | 'im'（默认 'event'）
ALTER TABLE value_segment ADD COLUMN source_mode TEXT;  -- 'personal' | 'enterprise'（仅 IM 场景）
ALTER TABLE value_segment ADD COLUMN im_chat_id UUID REFERENCES im_chat(id);
ALTER TABLE value_segment ADD COLUMN im_message_ids TEXT[];  -- 组成本段的原始消息 ID 列表
ALTER TABLE value_segment ADD COLUMN contributors JSONB;
-- contributors 结构: [{ user_id, name, anonymized, msg_count, segment_weight }, ...]

-- Skill 表新增字段（patch）
ALTER TABLE skill ADD COLUMN source_segment_ids UUID[];
ALTER TABLE skill ADD COLUMN contributors JSONB;
-- 同上
```

### 8.6 与 MVP Event Schema 的桥接

MVP §7.1 定义了统一 Event Schema（Claude Code / GitHub 等事件统一格式）。v0.3 选择**不把 IMMessage 强行转 Event**，而是：

- IMMessage 是独立流，专门走 SignalGate → IMValueSegment
- IMValueSegment 通过 `source_type='im'` 进入与 Event 同等地位的 ValueSegment 表
- 下游蒸馏管线对 ValueSegment 是同质处理，无需关心来源

**理由：** Event Schema 是面向"开发工具产生的结构化事件"（PR opened、conversation started），与"群聊消息流"形态差异大；强行映射会导致字段大量为空、语义扭曲。

---

## 9. 技术架构

### 9.1 整体拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                       TokenKnows 主体                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  ┌────────┐  │
│  │  Web     │  │  API     │  │  Generation   │  │ LLM    │  │
│  │  (React) │  │  (FastAPI)│  │  Pipeline     │  │Gateway │  │
│  └────┬─────┘  └────┬─────┘  └───────┬───────┘  └────────┘  │
│       │             │                │                       │
│       └─────────────┴────────────────┘                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴────────────────┐
        │   IMConnector Abstraction     │ ← 新增（v0.3）
        │   Interface (Python ABC)       │
        └──────────────┬────────────────┘
                       │
   ┌───────────────────┼────────────────────┐
   ▼                   ▼                    ▼
┌──────┐         ┌─────────┐          ┌──────────┐
│Feishu│         │DingTalk │          │  WeCom   │
│Adapter│        │Adapter  │          │Adapter   │
└──┬───┘         └────┬────┘          └─────┬────┘
   │                  │                     │
   │ OAuth +          │ Stream long-conn   │ C SDK
   │ Webhook          │ + REST              │ (subprocess)
   │                  │                     │
   ▼                  ▼                     ▼
┌─────────┐      ┌──────────┐         ┌──────────────┐
│ Feishu  │      │ DingTalk │         │  WeCom       │
│ OpenAPI │      │ OpenAPI  │         │ Finance SDK  │
└─────────┘      └──────────┘         └──────────────┘
```

### 9.2 IMConnector 抽象接口

```python
# code/tokenknows-api/src/im/connector_base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Optional

@dataclass(frozen=True)
class IMNormalizedMessage:
    """三家平台统一后的消息格式。"""
    platform_msg_id: str
    chat_id: str
    sender_user_id: str
    sender_name: Optional[str]
    msg_type: str          # 'text' | 'image' | 'file' | 'voice' | 'card' | 'system'
    content_text: Optional[str]
    content_meta: dict
    mentions: list[str]
    reply_to_msg_id: Optional[str]
    sent_at: datetime
    raw: dict              # 平台原始 payload（用于回溯调试，存数据库时丢弃）


class IMConnector(ABC):
    """所有 IM 适配器的统一接口。"""

    platform: str  # 'feishu' | 'dingtalk' | 'wecom'

    # --- OAuth / 授权 ---
    @abstractmethod
    async def get_authorize_url(self, connection_id: str, redirect_uri: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """换 access_token / refresh_token。返回 dict 由调用方落库。"""
        ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> dict: ...

    @abstractmethod
    async def revoke(self, access_token: str) -> None: ...

    # --- 会话与成员 ---
    @abstractmethod
    async def list_chats(self) -> list[dict]:
        """列出当前应用可见的所有 chat。"""
        ...

    @abstractmethod
    async def add_bot_to_chat(self, platform_chat_id: str) -> None: ...

    @abstractmethod
    async def list_chat_members(self, platform_chat_id: str) -> list[dict]: ...

    # --- 消息读取 ---
    @abstractmethod
    async def fetch_history(
        self, platform_chat_id: str, start: datetime, end: datetime
    ) -> AsyncIterator[IMNormalizedMessage]:
        """历史消息回填。AsyncIterator 自动分页。"""
        ...

    @abstractmethod
    async def stream_messages(self, platform_chat_id: str) -> AsyncIterator[IMNormalizedMessage]:
        """实时消息流。飞书/钉钉用 Webhook 推到统一队列后从此处出，企微用 SDK 主动拉。"""
        ...

    # --- 健康检查 ---
    @abstractmethod
    async def health(self) -> dict: ...
```

### 9.3 飞书适配器要点

```python
# code/tokenknows-api/src/im/feishu_adapter.py

class FeishuConnector(IMConnector):
    platform = "feishu"

    BASE_URL = "https://open.feishu.cn"

    async def get_authorize_url(self, connection_id, redirect_uri):
        # https://open.feishu.cn/document/uAjLw4CM/.../authorize
        scopes = "im:message,im:chat:readonly,im:chat,contact:user.id:readonly"
        return (
            f"{self.BASE_URL}/open-apis/authen/v1/authorize"
            f"?app_id={settings.FEISHU_APP_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&state={connection_id}"
            f"&scope={scopes}"
        )

    async def fetch_history(self, platform_chat_id, start, end):
        # GET /open-apis/im/v1/messages?container_id_type=chat&container_id={chat_id}
        # 分页字段: page_token / has_more
        page_token = None
        while True:
            params = {
                "container_id_type": "chat",
                "container_id": platform_chat_id,
                "start_time": int(start.timestamp()),
                "end_time": int(end.timestamp()),
                "page_size": 50,
                "page_token": page_token,
            }
            resp = await self._get("/open-apis/im/v1/messages", params=params)
            for item in resp["data"]["items"]:
                yield self._normalize(item)
            page_token = resp["data"].get("page_token")
            if not resp["data"]["has_more"]:
                break

    def _normalize(self, item: dict) -> IMNormalizedMessage:
        # 飞书消息内容是 JSON 字符串, 不同 msg_type 结构不同
        body = json.loads(item["body"]["content"])
        return IMNormalizedMessage(
            platform_msg_id=item["message_id"],
            chat_id=item["chat_id"],
            sender_user_id=item["sender"]["id"],
            sender_name=None,  # 飞书需要单独调 contact API 取名字
            msg_type=item["msg_type"],
            content_text=body.get("text"),
            content_meta=body,
            mentions=[m["id"]["open_id"] for m in item.get("mentions", [])],
            reply_to_msg_id=item.get("parent_id"),
            sent_at=datetime.fromtimestamp(int(item["create_time"]) / 1000),
            raw=item,
        )

    async def stream_messages(self, platform_chat_id):
        # 飞书无长连接, 走 Webhook + Redis Pub/Sub
        # /webhook/feishu 端点接收 → 验证签名 → publish 到 redis channel
        # 此处从 channel 订阅
        async for msg in self._subscribe_redis(f"im:feishu:chat:{platform_chat_id}"):
            yield msg
```

**关键点：**
- 飞书 Event Subscription 支持 Webhook 或 WebSocket。MVP 选 Webhook（简单、调试方便）
- Webhook URL: `/api/webhooks/feishu/{tenant_key}`，处理签名校验 + 解密 + 入队
- 实时事件用 Redis Pub/Sub 作为内部 fan-out

### 9.4 钉钉适配器要点

```python
class DingTalkConnector(IMConnector):
    platform = "dingtalk"

    async def stream_messages(self, platform_chat_id):
        # 钉钉用 Stream 模式（dingtalk-stream SDK 提供长连接）
        # 一个进程维护一个长连接, 所有 chat 共用
        async for raw_event in self._stream_client.iter_events():
            if raw_event["type"] == "IMReceiveMessage":
                msg = self._normalize(raw_event["data"])
                if msg.chat_id == platform_chat_id:
                    yield msg

    async def fetch_history(self, platform_chat_id, start, end):
        # POST /v1.0/im/sessions/messages
        # 注意: 钉钉历史消息接口在第三方企业应用场景有 30 天限制
        ...
```

**关键点：**
- Stream 模式需要长进程维护连接，建议独立 worker 进程（`im-stream-worker`）
- 钉钉的 user_id 体系复杂（unionid / userid / staff_id），需要做映射缓存
- 第三方企业应用的历史消息接口限 30 天，回填窗口要硬限制

### 9.5 企业微信适配器要点（最复杂）

```python
class WeComConnector(IMConnector):
    platform = "wecom"

    def __init__(self, connection: IMConnection):
        # C SDK 通过 ctypes 或 subprocess 调用
        # 推荐: NICEXAI/WeWorkFinanceSDK 的 Go 封装 + gRPC bridge
        self._sdk = WeWorkFinanceSDKBridge(
            corp_id=connection.wecom_corp_id,
            msgaudit_secret=decrypt(connection.wecom_msgaudit_secret_enc),
            private_key=decrypt(connection.wecom_private_key_enc),
            key_version=connection.wecom_private_key_version,
        )

    async def stream_messages(self, platform_chat_id):
        # 企微会话存档是 PULL 模式: 周期性调 GetChatData
        last_seq = await self._get_last_seq()
        while True:
            chunks = await self._sdk.get_chat_data(seq=last_seq, limit=1000)
            for chunk in chunks:
                # chunk = { encrypt_random_key, encrypt_chat_msg, seq, ... }
                random_key = self._sdk.rsa_decrypt(chunk["encrypt_random_key"])
                plain_msg = self._sdk.aes_decrypt(chunk["encrypt_chat_msg"], random_key)
                msg = self._normalize(plain_msg)
                if msg.chat_id == platform_chat_id:
                    yield msg
                last_seq = chunk["seq"]
            await self._set_last_seq(last_seq)
            await asyncio.sleep(5)  # 轮询间隔
```

**关键点：**
- **私有化部署强制：** C SDK 调用 `WXLoadMedia` 等需要本地文件系统、本地密钥；不能跑在多租户共享的 SaaS 实例
- 私钥管理：企业生成 RSA 密钥对，公钥上传企业微信，私钥存自家 HSM 或加密文件；TokenKnows 后端只持有"加密的私钥"，启动时密码解密到内存
- 多版本密钥：企业可能轮换密钥，SDK 必须支持 key_version → private_key 的映射
- 进程隔离：每个企业的 SDK 实例独立进程（C SDK 全局状态不安全）

### 9.6 SignalGate 实现

```python
# code/tokenknows-api/src/im/signal_gate.py

class SignalGate:
    def __init__(self, threshold: float = 0.4, llm_gateway: LLMGateway = ...):
        self.threshold = threshold
        self.llm = llm_gateway

    async def classify(self, msg: IMMessage, context: list[IMMessage]) -> SignalResult:
        # R1-R4: 强制 noise
        if self._rule_noise(msg):
            return SignalResult(is_signal=False, score=0.0, reason="rule:noise")

        # R6-R8: 强制 signal
        if self._rule_strong_signal(msg, context):
            return SignalResult(is_signal=True, score=0.9, reason="rule:strong")

        # R10: LLM 小模型分类
        prompt = self._build_classification_prompt(msg, context)
        llm_score = await self.llm.classify(
            prompt=prompt,
            model_hint="cheap",  # 路由到 Qwen2.5-3B 或类似小模型
        )
        return SignalResult(
            is_signal=llm_score >= self.threshold,
            score=llm_score,
            reason=f"llm:{llm_score:.2f}",
        )
```

**与 LLM Gateway 的协作：**
- SignalGate 调用走 `model_hint="cheap"` 路径
- LLM Gateway 路由表配置：`{ "cheap": "qwen2.5-3b-local" }`
- 单条分类成本 < 0.0001 美元（本地小模型几乎零边际成本）

### 9.7 部署形态

| 组件 | 部署方式 | 备注 |
| --- | --- | --- |
| Feishu Adapter | 同 API 主进程（uvicorn worker） | 无状态 |
| DingTalk Stream Worker | 独立 Docker 容器（`im-stream-worker`） | 长连接，每企业 1 个 |
| WeCom Adapter | 独立 Docker 容器 + C SDK 卷挂载 | 每企业 1 个，强制私有化 |
| Webhook 端点 | 同 API 主进程 | Feishu/DingTalk Webhook 共用 |
| SignalGate Worker | 独立 Celery worker（`im-signal-worker`） | 横向扩展 |
| 蒸馏 Worker | 复用 MVP 的 generation worker | 无需新增 |

```yaml
# docker-compose.im.yml 示例（叠加到 MVP 的 docker-compose.yml）
services:
  im-stream-worker:
    image: tokenknows/im-stream-worker:0.3.0
    environment:
      - REDIS_URL=...
      - DB_URL=...
    deploy: { replicas: 2 }

  wecom-adapter:
    image: tokenknows/wecom-adapter:0.3.0
    volumes:
      - /opt/wecom/sdk:/sdk  # C SDK 库
      - /opt/wecom/keys:/keys:ro  # 加密私钥
    environment:
      - WECOM_KEY_PASSWORD_FILE=/run/secrets/wecom_key_pass
    secrets: [wecom_key_pass]
    deploy: { replicas: 1 }

  im-signal-worker:
    image: tokenknows/im-signal-worker:0.3.0
    environment:
      - SIGNAL_THRESHOLD=0.4
      - LLM_GATEWAY_URL=http://api:8000/internal/llm
    deploy: { replicas: 4 }
```

---

## 10. API 设计

> 沿用 MVP TDD §6.1 的 REST 风格 + 鉴权（Bearer Token），新增 `/im/*` 命名空间。

### 10.1 IM 连接管理

```
POST   /api/projects/{pid}/im/connections
       创建 IM 连接（personal 模式）。返回 authorize_url 让前端跳转
       body: { platform: 'feishu', mode: 'personal' }
       resp: { connection_id, authorize_url }

POST   /api/projects/{pid}/im/connections/{cid}/exchange
       OAuth 回调后用 code 换 token
       body: { code }
       resp: { status: 'authorized' }

GET    /api/projects/{pid}/im/connections
       列出所有连接 + 状态 + 数据量

PATCH  /api/projects/{pid}/im/connections/{cid}
       暂停 / 恢复 / 修改配置
       body: { status?, config? }

DELETE /api/projects/{pid}/im/connections/{cid}
       撤回授权 + 触发 30 天数据清理
```

### 10.2 Chat 管理

```
GET    /api/projects/{pid}/im/connections/{cid}/chats
       列出该连接下所有可见的 chat（含未加入）
       query: ?status=active|paused|removed|available

POST   /api/projects/{pid}/im/connections/{cid}/chats/{platform_chat_id}/join
       邀请 bot 入群

POST   /api/projects/{pid}/im/connections/{cid}/chats/{cid}/leave
       踢出 bot

GET    /api/projects/{pid}/im/chats/{chat_id}/stats
       会话统计: 消息数 / signal 率 / TOP contributors
```

### 10.3 消息查询（受权限控制）

```
GET    /api/projects/{pid}/im/chats/{chat_id}/messages
       查询消息（仅当前用户有权限的）
       query: ?since=...&until=...&is_signal=true&page=...
       注意: 默认不返回 content_text（隐私敏感），需 explicit ?include_content=true 且权限校验

GET    /api/projects/{pid}/im/messages/{msg_id}
       单条消息详情
```

### 10.4 SignalGate

```
GET    /api/projects/{pid}/im/signal/config
PATCH  /api/projects/{pid}/im/signal/config
       body: { threshold: 0.4 }

POST   /api/projects/{pid}/im/signal/recompute
       重算指定时间段的 SignalGate（threshold 变更后用）
       body: { chat_id?, since, until }
```

### 10.5 同意书

```
GET    /api/projects/{pid}/im/consents
       列出本项目的同意书状态（管理员视角）
       query: ?status=pending|agreed|declined|revoked

POST   /api/projects/{pid}/im/consents/send
       批量发送同意书
       body: { user_ids: [...], delivery_method: 'email' | 'im_dm' }

POST   /api/projects/{pid}/im/consents/{cid}/sign
       员工签字（员工自己调）
       body: { signature_meta }

POST   /api/projects/{pid}/im/consents/{cid}/revoke
       撤回同意（员工自己或代签）
```

### 10.6 按需蒸馏

```
POST   /api/projects/{pid}/im/distill
       主动按需触发蒸馏
       body: { chat_id, since, until, mode: 'segments' | 'skill' | 'asset_chapter' }
       resp: { task_id, eta_seconds }

GET    /api/tasks/{task_id}  # 复用 MVP 任务接口
```

### 10.7 Webhook 入口

```
POST   /api/webhooks/feishu/{tenant_key}
POST   /api/webhooks/dingtalk/{corp_id}
       平台事件回调入口
       请求体含加密签名, 由各 Adapter 自行校验解密
```

### 10.8 SSE 推送

复用 MVP §6.2 的 SSE。新增事件类型：
- `im.message.received` (聚合，每 30 秒推一次摘要，避免刷屏)
- `im.signal.computed` (每 N 条触发)
- `im.distill.completed`
- `im.consent.signed` / `im.consent.revoked`

---

## 11. 安全实现

### 11.1 凭据加密

| 凭据 | 加密方式 | 存储位置 |
| --- | --- | --- |
| access_token / refresh_token | AES-256-GCM（KMS 主密钥） | im_connection 表 |
| WeCom RSA 私钥 | 二级加密：密码派生密钥（PBKDF2） + KMS | im_connection 表 + 独立 secret store |
| WeCom 私钥解锁密码 | Docker Secret / Vault / 启动时人工输入 | 不入库 |

### 11.2 鉴权与授权

| 操作 | 必需权限 |
| --- | --- |
| 创建/查看自己的 personal connection | 项目成员（Owner/Editor/Reviewer/Viewer 均可） |
| 创建/管理 enterprise connection | 仅 Owner |
| 发送同意书 | 仅 Owner |
| 查看消息原文 | 消息发送者本人 + Owner（审计目的） |
| 查看 ValueSegment（含 IM 来源） | 项目成员，但需求贡献者已 agreed |

### 11.3 同意书数字签名

签字必须留存证据：
- IP / UA / 时间戳
- 同意书文本版本号（变更必须重签）
- 签字方法（OAuth click / Email link / OA form）
- 多种证据组合可上链或存到 audit_log（可选）

### 11.4 审计日志

复用 MVP TDD §5.4 的 audit_log 表，新增 event types:
- `im.connection.created` / `revoked`
- `im.consent.sent` / `signed` / `revoked`
- `im.message.read` (高频，仅记 chat 级 daily 聚合)
- `im.message.exported`
- `im.distill.triggered`

### 11.5 出域控制（数据安全）

| 数据 | 出域规则 |
| --- | --- |
| IMMessage.content_text 原文 | **绝不出域** |
| IMMessage 元数据（时间/发送者/类型） | 项目导出时可选包含 |
| ValueSegment.content（脱敏后） | 同 MVP，需 D5 脱敏确认 |
| Skill.skill_md | 同 MVP §5.8 |

**LLM 调用控制：**
- SignalGate 默认走本地小模型，不出域
- 蒸馏可选走云端大模型，但消息原文必须经过 MVP §6.6 的 LLM Gateway 脱敏中间件
- 企业管理员可强制"全本地 LLM"模式（关闭云端出口）

---

## 12. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- | --- |
| R1 | 平台 API 变动 | 中 | 中 | IMConnector 抽象隔离；3 家平台版本号锁定；CI 监控 API 弃用通知 |
| R2 | 员工大面积拒签 | 中 | 高 | 个人模式（A）先行培养信任；同意书强调"非强制、可撤回" |
| R3 | 企业微信 SDK 集成复杂 | 高 | 中 | v0.3.2 才做；预留 buffer；考虑买现成 SDK 服务（如 mochat） |
| R4 | 群聊噪声率超预期，LLM 成本爆 | 中 | 中 | SignalGate 双层（规则 + 小模型）；本地小模型默认；按月配额上限 |
| R5 | 撤回风暴导致已蒸馏 skill 大量失去贡献者 | 低 | 中 | skill 不删除，只做匿名化；保留 1 个月可恢复窗口 |
| R6 | 蒸馏出有偏见/不当内容 | 低 | 高 | 复用 MVP §5.6 脱敏 + Reviewer 流程；首次启用 30 天人工审 100% |
| R7 | 企业微信涨价（2026-01-22 已 100% 涨幅）导致 ROI 不达预期 | 高 | 中 | 在销售话术中说明价格构成；引导客户先试飞书 / 钉钉 |
| R8 | 长连接断开导致消息丢失 | 中 | 中 | 钉钉 Stream 自动重连 + 断点续传（last_seq）；企微每 5 秒拉取 + seq 持久化 |
| R9 | Webhook 重放攻击 | 低 | 中 | 签名校验 + nonce + 时间戳（5 分钟窗口） |
| R10 | 数据保留期到期前未通知 | 低 | 高 | 定时任务每天扫描 retention_until，到期前 7 天通知；到期硬删除 |
| R11 | 多个 IMConnection 蒸馏出冗余 skill | 中 | 低 | 复用 MVP §5.8 的 skill 去重逻辑（cosine 阈值） |
| R12 | 个人模式数据归属纠纷（用户离职带走自己的 skill） | 中 | 中 | TOS 明文：personal mode → 用户拥有；enterprise mode → 企业拥有；导出时显式确认 |

---

## 13. 发布里程碑

### 13.1 v0.3.0 · 飞书个人助理模式（MVP 阶段）

**范围：**
- 飞书 OAuth 接入（个人用户）
- 群组选择 + 机器人入群
- 历史消息回填（7 天）
- 实时 Webhook 接入
- SignalGate（规则 + 本地 LLM）
- 蒸馏到 ValueSegment / Skill（复用 MVP 管线）
- 基础 UI：连接卡片、群列表、统计仪表板

**不在范围：**
- 钉钉 / 企业微信
- 企业模式 / 同意书
- @ 机器人按需蒸馏

**预计周期：** 2-3 sprint（5-7 周）

**验收 AC：**
- 1 个真实试点用户 30 天数据：≥ 80% 用户能成功授权并完成首次蒸馏
- SignalGate 准确率：人工抽样 100 条，误判率 < 15%
- 蒸馏延迟：从消息发出到 ValueSegment 入库 < 5 分钟（实时）；历史回填 < 24 小时

### 13.2 v0.3.1 · 飞书企业会话存档模式

**范围：**
- 飞书企业自建应用支持
- 同意书生命周期管理（IM-D）
- 群/人员双白名单
- 数据保留期与到期清理
- 撤回流程
- 管理员仪表板（IM 数据健康度）

**预计周期：** +2 sprint

### 13.3 v0.3.2 · 钉钉双模式

**范围：**
- 钉钉适配器（Stream 模式 + REST）
- 复用 v0.3.0 / v0.3.1 的所有功能

**预计周期：** +2 sprint

### 13.4 v0.3.3 · 企业微信会话存档

**范围：**
- WeCom C SDK 集成（Docker 容器化）
- RSA 密钥管理 + 启动密码
- 私有化部署文档完善

**预计周期：** +2-3 sprint

### 13.5 v0.3.4 · @ 机器人按需蒸馏

**范围：**
- 三家平台统一的群 @ 命令解析
- `/distill <时间窗口>` 等命令
- 即时蒸馏 + deeplink 回执

**预计周期：** +1 sprint

---

## 14. 开放问题与决策状态

> 2026-05-22 已决 4 条（Q1/Q3/Q4/Q7）→ v0.3.0 研发可启动。
> 剩余 4 条（Q2/Q5/Q6/Q8）由 v0.3.1+ 启动前再确认。

| # | 问题 | 状态 | 最终决策 / 选项 |
| --- | --- | --- | --- |
| Q1 | v0.3.0 上线后是直接公测还是闭门试点？ | ✅ **已决（2026-05-22）** | **5 家定向试点 30 天**，反馈完成后小范围公测；试点期收集 SignalGate 准确率数据用于校准 §15 附录 C |
| Q2 | 个人模式下，用户能否把自己蒸馏的 skill 共享到团队？ | ⏳ 待 v0.3.1 决 | 倾向：默认私有 + 显式分享（保护用户） |
| Q3 | 历史消息回填的时间窗口默认是？ | ✅ **已决（2026-05-22）** | **7 天**，用户可在数据源设置里手动调长（上限 90 天） |
| Q4 | SignalGate 用什么本地小模型？ | ✅ **已决（2026-05-22）** | **Qwen2.5-3B（4-bit 量化）**；GGUF 格式，通过 llama.cpp 或 Ollama 部署；Apache 2.0 商用 OK |
| Q5 | 企业微信 v0.3.2 的私钥管理走 HSM 还是本地加密文件？ | ⏳ 待 v0.3.2 决 | 倾向：双方案，默认文件，HSM 作为企业版选项 |
| Q6 | 蒸馏后的 Asset/Skill 在 IM 群里要不要自动 @ 通知贡献者？ | ⏳ 待 v0.3.4 决 | 倾向：默认关闭，用户可开 |
| Q7 | 数据保留期默认 90 天是否合理？ | ✅ **已决（2026-05-22）** | **90 天**；与 SOC2 / ISO27001 常见配置对齐；同意书模板（附录 B）已按此填写 |
| Q8 | 是否允许跨项目复用 IM 蒸馏出的知识？ | ⏳ 待 v0.3.1 决 | 倾向：默认禁止（避免跨项目数据泄漏），管理员可放开 |

---

## 15. 附录

### 附录 A · 平台 API 速查表

#### A.1 飞书

| 用途 | Endpoint / Event | 文档 |
| --- | --- | --- |
| OAuth 授权 | `GET /open-apis/authen/v1/authorize` | [link](https://open.feishu.cn) |
| 历史消息 | `GET /open-apis/im/v1/messages` | [link](https://open.feishu.cn/document/server-docs/im-v1/message/list) |
| 单条消息 | `GET /open-apis/im/v1/messages/{message_id}` | [link](https://open.feishu.cn/document/server-docs/im-v1/message/get) |
| 群列表 | `GET /open-apis/im/v1/chats` | - |
| 群成员 | `GET /open-apis/im/v1/chats/{chat_id}/members` | - |
| Bot 入群 | `POST /open-apis/im/v1/chats/{chat_id}/members` | - |
| 接收消息事件 | `im.message.receive_v1` | [link](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive) |
| 事件订阅 | Webhook 或 WebSocket | [link](https://open.feishu.cn/document/server-docs/event-subscription-guide/overview) |

#### A.2 钉钉

| 用途 | Endpoint / Event | 文档 |
| --- | --- | --- |
| API 总览 | - | [link](https://open.dingtalk.com/document/isvapp/api-overview) |
| Stream SDK | `dingtalk-stream` | [link](https://open-dingtalk.github.io/developerpedia/docs/develop/sdk/overview/) |
| 接收消息事件 | `IMReceiveMessage` | - |
| 群消息 | `POST /v1.0/robot/groupMessages/send` | [link](https://open.dingtalk.com/document/orgapp-server/the-robot-sends-a-group-message) |
| 历史消息 | `/v1.0/im/sessions/messages` | - |

#### A.3 企业微信

| 用途 | Endpoint / Event | 文档 |
| --- | --- | --- |
| 会话存档主页 | - | [link](https://developer.work.weixin.qq.com/document/path/91774) |
| 获取会话数据 | C SDK `GetChatData` | 同上 |
| 解密数据 | C SDK `DecryptData` | 同上 |
| 主流 SDK | NICEXAI/WeWorkFinanceSDK (Go) | [link](https://github.com/NICEXAI/WeWorkFinanceSDK) |
| 价格（2026-01-22 起） | 办公版 400 / 服务版 900 / 企业版 1800 元/人/年 | [link](https://work.weixin.qq.com/nl/act/p/9856d9e431164012) |

### 附录 B · 员工同意书模板

```
                员工 IM 会话内容处理同意书

       （TokenKnows v{TPL_VERSION} · 适用于本企业 {COMPANY_NAME}）

一、处理者：
  甲方（处理者）：{COMPANY_NAME}
  技术服务方：TokenKnows ({TOKENKNOWS_LEGAL_ENTITY})

二、本同意书覆盖的范围：
  - 平台：{PLATFORM}
  - 群组：{CHAT_LIST}（共 N 个）
  - 时间段：从 {START_DATE} 起，持续至本同意书撤回
  - 数据类型：{DATA_TYPES}（仅文本，不含语音/视频原文）

三、处理目的：
  仅用于本企业范围内的知识资产蒸馏、文档自动生成、专家知识沉淀。
  不用于：员工绩效评估、个人画像、对外销售。

四、数据保留期：
  - 原始消息：90 天（到期自动删除）
  - 蒸馏后的资产（脱敏后）：无限期，除非您撤回同意

五、您的权利：
  - 随时撤回（撤回方式：TokenKnows 个人设置 / 联系本企业 HR）
  - 查询自己被处理的范围
  - 申请匿名化（保留贡献，但不显示您的姓名）

六、不参与的后果：
  - 您的消息将不被蒸馏
  - 不影响您的劳动合同、薪资、晋升等任何雇佣关系条款

七、签字：
  员工姓名：__________
  飞书/钉钉/企微 ID：__________
  日期：__________
  签字方式：[ ] OAuth 点击同意  [ ] 邮件链接  [ ] OA 表单
```

### 附录 C · 信噪比基线数据（v0.3 假设值，需 v0.3.0 灰度后校准）

| 场景 | 假设 signal 率 | 缓解 |
| --- | --- | --- |
| 技术工作群（10-30 人） | 25% | 默认阈值 0.4 |
| 跨团队大群（50+ 人） | 10% | 建议提高阈值到 0.5 |
| 项目临时群（< 10 人） | 35% | 默认 0.4 即可 |
| 1-on-1 私聊 | 50% | 默认 0.4 |

> v0.3.0 灰度结束后用真实数据替换。

---

## 16. 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.3-draft.1 | 2026-05-22 | 初稿，含飞书 / 钉钉 / 企业微信三家完整方案 |
| v0.3-draft.2 | 2026-05-22 | 确认 4 项关键决策（Q1/Q3/Q4/Q7）→ IM-11~14 写入决策表；§14 状态更新；v0.3.0 研发可启动 |

---

**Sources / 参考：**
- 飞书开放平台 · 历史消息 API · https://open.feishu.cn/document/server-docs/im-v1/message/list
- 飞书开放平台 · 事件订阅 · https://open.feishu.cn/document/server-docs/event-subscription-guide/overview
- 钉钉开放平台 · API 总览 · https://open.dingtalk.com/document/isvapp/api-overview
- 钉钉 SDK 概述 · https://open-dingtalk.github.io/developerpedia/docs/develop/sdk/overview/
- 企业微信 · 获取会话内容 · https://developer.work.weixin.qq.com/document/path/91774
- 企业微信 · 会话存档涨价公告（2026-01-22）· https://work.weixin.qq.com/nl/act/p/9856d9e431164012
- WeWorkFinanceSDK (Go 封装) · https://github.com/NICEXAI/WeWorkFinanceSDK
- 飞书 oapi-sdk-python · https://github.com/larksuite/oapi-sdk-python
