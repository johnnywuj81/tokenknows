# Proposal · TokenKnows v0.4 · 自动生成触发与类型路由

> 单独提案文档 — 把"事件累积 / 时间窗口 / 信号识别"转化为**自动触发文档与 Skill 生成**的能力，补齐 PRD 决策 #4 与 #7 在 MVP 阶段没实施的部分。

---

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | TokenKnows v0.4 · 自动生成触发与类型路由 产品技术方案 |
| 文档版本 | v0.4-draft.1（起草中） |
| 文档状态 | 起草中 · 待用户评审 |
| 撰写日期 | 2026-05-22 |
| 关联文档 | [PRD MVP](./PRD_TokenKnows_MVP.md) · [TDD MVP](./TDD_TokenKnows_MVP.md) · [v0.3 IM 提案](./Proposal_IM_KnowledgeDistillation_v0.3.md) · [BRD](./BRD_AI研发知识资产引擎.md) |
| 目标读者 | 产品、研发、运营 |
| 体例 | PRD + TDD 一体；§3-§7 偏产品，§8-§13 偏技术 |

### 1.1 与 v0.3 / MVP 的关系

| 维度 | MVP（v0.1-v0.2） | v0.3 IM | **本提案（v0.4）** |
| --- | --- | --- | --- |
| 文档生成触发方式 | 仅手动 | 仅手动 | **+ 定时 + 事件 + 阈值 + @ 机器人**（PRD #4 三种触发真落地） |
| 类型确定方式 | 用户在 Dialog 里手选 | 同上 | **基于触发信号的自动路由 + 用户可覆盖** |
| Skill 蒸馏触发 | 用户传 chapter_ids 手动调 | 同上 | **章节累积阈值自动触发 + 用户可关闭** |
| Skill 自进化触发 | 代码有 `should_evolve()` 但无 cron 调它 | 同上 | **接入调度器自动跑** |
| 部署增量 | — | IM Connector 容器 | **+ APScheduler 进程**（小依赖）+ trigger_rules 表 |
| LLM 用量 | 完全用户触发，可控 | 同上 | **需要资源配额（月 token 上限）+ 频率限制** |

### 1.2 关键决策表（v0.4）

| # | 决策 | 取值 | 备注 |
| --- | --- | --- | --- |
| AT-1 | 调度器选型 | **APScheduler 4.x**（in-process AsyncIO scheduler） | 单实例足够；多实例时切到 PostgreSQL JobStore；不引入 Celery Beat / Redis 重依赖 |
| AT-2 | 触发模式 | **5 种并存**：手动 / 定时 / 事件 / 阈值 / @ 机器人 | 与 PRD #4 对齐；@ 机器人复用 v0.3.4 接口 |
| AT-3 | 类型路由策略 | **优先级规则匹配 + LLM fallback** | 规则命中优先；都不命中走 LLM 推断（带 confidence，低于阈值不触发） |
| AT-4 | 用户覆盖权 | **所有自动触发都生成 draft 状态**，用户可在 5 分钟"撤回窗口"内取消 | 防止误触发，撤回期内自动延迟实际 LLM 调用 |
| AT-5 | 审批闸门 | **自动生成 ≠ 自动发布**；自动生成的 asset 必须经 Reviewer 审批才能 publish | 与 MVP §4.3 审批流强绑定，不开后门 |
| AT-6 | 频率限制 | **每规则每小时最多 1 次触发**；同类型最多每天 5 份 | 防止规则风暴（如 PR webhook 风暴） |
| AT-7 | 资源配额 | **每项目每月 LLM token 配额**（管理员可配） | 超额自动暂停所有规则；不能让一个项目跑炸整个实例 |
| AT-8 | 规则可配置 | **UI 配置面板**（无需改代码即可启停 / 调阈值 / 改类型路由） | 决策权交给项目 Owner |
| AT-9 | 默认规则 | **预置 4 条**：周一周报 / PR 标 architecture / Issue 标 incident / 累积 50 章 book | 新项目零配置即用 |
| AT-10 | 回滚机制 | **5 分钟撤回窗口** + 所有自动生成进 audit_log 可一键归档 | 用户随时可关单条规则 + 删除已生成草稿 |

### 1.3 体验要素新增

延续 MVP / v0.3 体验要素编号，v0.4 新增：

| # | 要素 | 出现位置 |
| --- | --- | --- |
| 29 | 自动触发规则可视化（项目设置内列表 + 启停切换） | §7.4 / §8.1 |
| 30 | "5 分钟撤回窗口"通知卡（生成开始前可取消） | §7.5 / §8.2 |
| 31 | 触发执行历史时间轴（哪条规则、什么时候、产出什么） | §7.5 |
| 32 | LLM 月配额仪表盘（管理员可见用量 + 预警） | §11.3 |
| 33 | 自动生成 asset 上的"自动触发"徽标（区别于手动） | §8.3 |
| 34 | 类型路由结果可解释（每份自动生成的 asset 显示"为什么是这个类型"） | §7.2 |
| 35 | 默认规则向导（首次启用 v0.4 时引导用户选 4 条预置规则） | §6.1 / §7.4 |

---

## 2. 关键约束（前置，决定方案形态）

把 v0.4 做成"能用"而不是"扰民"的产品，三条硬约束必须先定下来。

### 2.1 频率约束（最强约束）

**问题来源**：自动触发一旦失控，会产生两种灾难：
- **LLM 账单爆炸**：一个 PR webhook 风暴 → 100 次同类规则触发 → 100 次 LLM 调用 → 一晚上烧光月预算
- **审批队列堆积**：自动生成 100 份草稿 → Reviewer 看到面板里全是待审 → 直接放弃 → 系统失信

**对方案的强制要求：**

1. **每规则每小时最多 1 次触发**（AT-6）。规则在 cooldown 期内被再次满足时跳过，仅写 trigger_execution（reason=cooldown），不调 LLM
2. **同类型每天最多 5 份**（AT-6）。例如某天连续 5 个 PR 触发了 ADR 自动生成，第 6 个不再生成，写 audit_log（reason=quota_daily）
3. **5 分钟撤回窗口**（AT-4）。触发命中规则后**不立即调 LLM**，先在数据库写 `trigger_execution { status=scheduled, fire_at=now+5min }`，UI 显示通知卡"5 分钟后将生成 XX 类型文档，点取消"；窗口期内 LLM 不被调用
4. **资源配额硬墙**（AT-7）。每项目每月 LLM token 配额，超额所有规则自动 paused，给 Owner 邮件告警

### 2.2 类型路由约束

**问题**：5 种触发信号 + 6 种文档类型 + 1 种 Skill 类型，组合关系不能含混。

**对方案的强制要求：**

1. **优先级 + 互斥**：规则按 priority 排序，**只取最高优先级命中的那条**，不并行触发多个类型
2. **每条规则有唯一类型**：不能有"既可能生成 weekly_report 又可能生成 incident"的模糊规则
3. **LLM fallback 必须有 confidence**：当规则都不命中走 LLM 推断时，confidence < 0.7 → 不触发；记 audit_log（reason=low_confidence）
4. **可解释性硬要求**（要素 #34）：每份自动生成的 asset 必须能告诉用户"为什么是这个类型"——存 `asset.trigger_meta = { rule_id, signal, confidence }`

### 2.3 审批闸门约束

**问题**：如果自动生成跳过 Reviewer 直接发布，知识库会被 LLM 错误 / 幻觉污染，整个产品价值崩塌。

**对方案的强制要求：**

1. **自动生成 ≠ 自动发布**（AT-5）。所有自动生成的 asset 默认 `status=draft`，与手动生成走**完全相同**的审批流
2. **不开"自动审批"后门**。哪怕规则触发了 100 次产出 100 份周报，全部需要 Reviewer 逐份审批
3. **降级路径**：审批超时（默认 7 天无 reviewer 动作）的自动生成 asset 自动归档（status=archived），不堆积

---

## 3. 产品概述

### 3.1 定位与价值

**一句话定位：** 让 TokenKnows 从"用户主动点按钮"的工具，进化为"研发过程自动产出周报、复盘、ADR、技能"的**研发后台代理**——用户接入数据源后，**不需要每天提醒自己**"该写周报了 / 该复盘那次 incident 了"。

**为什么 v0.4 是关键节点：**

| 阶段 | 用户认知 | 留存特征 |
| --- | --- | --- |
| MVP（手动）| "是个文档编辑器 + LLM 写作助手" | 周活 1-2 次，多数用户接入后忘了 |
| v0.3 IM | "+ 一个数据源接入" | 留存改善但仍然 reactive |
| **v0.4 自动触发** | "**它在替我盯着团队的过程数据，没我也在产出**" | 真正变成"开机就开"的后台系统 |

**价值主张三件套（与 MVP §3.1 对齐 + 增强）**

- **当天可见 → 每天可见**：阈值自动触发"首份"周报（MVP §3.1 承诺）扩展为"每周自动周报、每次 incident 自动复盘"
- **可信可溯**：自动生成不绕过审批流，证据链与手动生成完全一致
- **可控可解释**：每条规则可启停、可调阈值；每份产出可解释"为什么这个类型 / 为什么这个时间"

### 3.2 MVP 范围（v0.4.0 ~ v0.4.4 渐进交付）

| 版本 | 范围 | 预计周期 |
| --- | --- | --- |
| **v0.4.0** | 定时触发（cron）+ 默认"周一 09:00 自动周报" + UI 配置面板（只读列表）+ 撤回窗口 | 2 sprint |
| v0.4.1 | 事件触发（GitHub webhook）+ PR 标 `architecture` → ADR，Issue 标 `incident` → 复盘 | +2 sprint |
| v0.4.2 | 阈值触发（累积章节）+ 50 章 approved → book / IM signal 累积 → skill | +1 sprint |
| v0.4.3 | UI 配置面板完整版（用户可新建 / 编辑 / 启停规则） | +1 sprint |
| v0.4.4 | 资源配额仪表盘 + 月 token 上限管理 + 告警 | +1 sprint |

> **Out of scope（v0.4 不做）：**
> - 多实例调度（要 v0.5 上 PostgreSQL JobStore）
> - 自定义 DSL 编辑器（v0.4 规则用预置 builder 模板）
> - 跨项目共享规则（v0.5+）
> - 自动发布（永不做，违反 AT-5）

### 3.3 目标用户

| 角色 | 价值 | 阻力 | 切入点 |
| --- | --- | --- | --- |
| Owner（Tech Lead）| "团队每周都有周报，新人 onboarding 资料自动累积" | 担心 LLM 烧钱 / 担心产出垃圾 | 月配额仪表盘 + 5 分钟撤回 + Reviewer 必经 |
| Editor | "不需要每周一手动点生成；PR 提了 architecture 改动自动有 ADR 草稿" | 担心被自动生成的草稿淹没 | 通知聚合（每天一份"今天有 X 份草稿待审"摘要）+ 可关单条规则 |
| Reviewer | "自动产出意味着我审批量增加，但都是结构化的，比看 PR 快" | 审批量增加 | 默认 5 分钟撤回窗口阻断 70% 误触发；规则启用前预估每周产出量 |
| 实例管理员 | "可视化用量、按项目设配额、看见全局成本曲线" | 担心一个项目跑炸全实例 | 实例级硬上限 + 项目级软配额 |

---

## 4. 触发模式矩阵（5 种触发并存）

> v0.4 的核心是把 PRD 决策 #4 的"手动 + 定时 + 事件"三种触发，**实际跑起来**——并在三者之上加入"阈值"和"@ 机器人"。

| 模式 | 信号源 | 周期 / 时机 | 典型场景 | v0.4 子版本 |
| --- | --- | --- | --- | --- |
| **M1 手动** | 用户点击 | 即时 | 用户主动生成新文档 | 已有（v0.1） |
| **M2 定时（cron）** | APScheduler cron 表达式 | 周期，如每周一 09:00 | 每周自动周报、每月技术月报 | v0.4.0 |
| **M3 事件（webhook）** | GitHub webhook / IM event / 内部事件总线 | 事件到达时 | PR merge → 触发 ADR 草稿；Issue labeled incident → 触发复盘 | v0.4.1 |
| **M4 阈值（累积）** | 数据库 polling（每 15 分钟扫一次） | 累积量越过阈值时 | 累积 50 章 approved → book；某专家在某 topic 累积 20 条 signal → skill | v0.4.2 |
| **M5 @ 机器人按需** | IM 群里 @TokenKnows | 即时 | @机器人 `/distill 最近 2 小时` | 复用 v0.3.4（已规划） |

**关键设计**：5 种触发不耦合，共享同一个 `trigger_rule` 表 + 同一个 `dispatch_generation()` 服务调用。区别只在"信号源"。

---

## 5. 类型路由规则表（核心）

### 5.1 信号 → 类型 决策表

> 这是 v0.4 的灵魂——每条信号对应到一个产出类型。规则按 priority 从高到低评估，只取最高命中。

| Priority | 触发模式 | 信号特征 | 产出类型 | 默认是否启用 |
| --- | --- | --- | --- | --- |
| 100 | M3 事件 | GitHub Issue 新建且 labels 含 `incident` 或 `outage` | `incident`（问题复盘） | ✅ |
| 95 | M3 事件 | GitHub Issue 关闭且 labels 含 `incident` | `incident`（复盘补全） | ✅ |
| 90 | M3 事件 | PR merged 且 files changed 含 `**/ARCHITECTURE.md` 或 `docs/design/**` | `tech_design`（技术方案） | ✅ |
| 85 | M3 事件 | PR merged 且 title 含 `[ADR]` 或 labels 含 `architecture-decision` | `adr`（架构决策记录） | ✅ |
| 80 | M3 事件 | IM SignalGate 命中 R7（决策表述）连续 ≥ 5 条同主题 | `adr` | ⏸ 默认关 |
| 70 | M4 阈值 | 项目累积 ≥ 50 章 approved 且未生成过 book | `book`（书籍长文档） | ⏸ 默认关（需 Owner 显式启用） |
| 60 | M4 阈值 | 某 user_id 在某 topic ≥ 20 条 IM signal 且 acceptance_rate ≥ 0.8 | `agent_skill`（Skill 蒸馏） | ✅（v0.4.2+） |
| 50 | M2 定时 | 每周一 09:00 且上周 events ≥ 30 | `weekly_report` | ✅ |
| 30 | M2 定时 | 每月 1 日 09:00 且当月 events ≥ 100 | `weekly_report`（月报变体）| ⏸ 默认关 |
| 10 | M5 @ 机器人 | 任意 @ 命令 | 由命令参数指定 | ✅ |

### 5.2 多信号冲突仲裁

**场景**：周一 09:00（M2 触发周报）+ 同时刚 merge 一个 architecture PR（M3 触发 ADR）—— 同一项目同一时间被两条规则命中。

**仲裁规则**：

1. **不同类型不冲突**：周报 + ADR 是两个独立 asset，**并行触发**（各自独立通过频率限制）
2. **同类型只取最高优先级**：如果同时被 priority=95（Issue 关闭复盘）和 priority=100（Issue 新建复盘）命中——只取 100；写 trigger_execution 备注"规则 95 被 100 覆盖"
3. **5 分钟撤回窗口聚合**：同一项目 5 分钟内多个 draft 进入撤回窗口 → UI 聚合成一张"待生成 N 份"通知卡，不刷屏

### 5.3 规则可配置性

**v0.4.0**（最小可见）：上面那张表"硬编码"在 `app/services/auto_trigger/default_rules.py`，UI 配置面板**只读列出 + 启停 toggle**，不能改阈值

**v0.4.3**（完整）：UI 允许用户：
- 改 priority（重排序）
- 改阈值（如把"PR labels 含 architecture-decision"改成"含 architecture 或 design-doc"）
- 新建规则（基于 builder 模板，非自由 DSL）
- 删除规则

---

## 6. 核心用户旅程

### 6.1 旅程 A · 周一定时周报（v0.4.0 主流程）

> 阿强是 Acme 后端组的 Tech Lead，刚启用 v0.4。

```
1. 阿强在工作台看到首次 v0.4 引导卡："启用自动触发？预置 4 条规则推荐给你..."
2. 阿强点开看（要素 #35）→ 默认勾选 weekly_report + ADR + incident 三条，
   book 默认未勾（怕首次试用就 token 烧太多）→ 点"启用"
3. 后端在 trigger_rules 表插入 3 条 enabled=true 记录
4. 周日晚 23:55, APScheduler scheduler 检查 weekly_report 规则的下次 fire_at
5. 周一 09:00:00, scheduler 触发 weekly_report 规则
6. 触发引擎检查：上周事件数 = 87 ≥ 30 → 命中
7. 写 trigger_execution { status=scheduled, fire_at=09:05:00 }
8. 前端 SSE 推送 "5 分钟后将自动生成周报 · Week 22"（要素 #30）
9. 阿强收到通知 → 觉得 OK → 不点取消
10. 09:05:00 撤回窗口结束 → 调 LLM Gateway → 生成 weekly_report (status=draft)
11. asset.trigger_meta = { rule_id, signal: 'weekly_cron', confidence: 1.0 }
12. asset 上有"自动触发"徽标（要素 #33）
13. 阿强点开 → 看到完整周报草稿 → 编辑 → 提交审批
14. Reviewer 通过 → 发布
```

**关键交互点：**
- 步骤 2：引导向导 → 要素 #35
- 步骤 8：撤回窗口通知 → 要素 #30
- 步骤 11-12：可解释 + 徽标 → 要素 #33, #34

### 6.2 旅程 B · PR 触发 ADR（v0.4.1）

> Acme 后端组刚 merge 一个 PR，标题 `[ADR] Switch from Postgres to ClickHouse for analytics`。

```
1. GitHub webhook 推送 PR merged 事件到 /api/webhooks/github
2. 事件入 events 表 (event_type=pr_merged)
3. 触发引擎扫描 enabled rules，命中 priority=85 规则（PR title 含 [ADR]）
4. 写 trigger_execution { rule_id=adr-pr-title, status=scheduled, fire_at=now+5min }
5. 前端 SSE 推送 "5 分钟后将生成 ADR 草稿 - 由 PR #1234 触发"
6. 5 分钟后调 LLM → 拉 PR 的 description + commits + files changed → 生成 ADR 草稿
7. asset.trigger_meta = { rule_id, signal: 'github_pr', evidence: ['pr_1234'], confidence: 1.0 }
8. 通知 Editor 审阅
```

### 6.3 旅程 C · Incident 触发复盘（v0.4.1）

```
1. 某周二凌晨 02:13 production 出问题 → on-call 在 GitHub 新建 Issue 标 incident
2. GitHub webhook → 触发引擎命中 priority=100 → 写 trigger_execution
3. 5 分钟撤回窗口（凌晨 02:18 自动触发）
4. 复盘草稿生成: 拉 Issue 描述 + 关联 PR + Sentry 链接 + 时间窗口内 IM 讨论
5. 早上 09:00 on-call 上班 → 看见自动产出的复盘草稿 → 补充实际处理过程 → 提审
6. 如果 Issue 关闭时还没生成复盘（很罕见），priority=95 兜底再触发一次
```

### 6.4 旅程 D · 累积章节触发 book（v0.4.2）

```
1. M4 阈值扫描器每 15 分钟跑一次
2. 第 N 次扫描: 检测到 project_X 的 approved chapter 数 = 50, 之前从未生成 book
3. 命中 priority=70 规则 → 写 trigger_execution
4. UI 通知 Owner: "你的项目累积了 50 个高质量章节, 是否要自动生成一本内部技术手册?"
   (book 类型涉及大量 LLM token, 默认需要 Owner 确认, 非默认 fire)
5. Owner 确认 → 跳到 BookGenerationDialog (复用 v0.2) → 选模板 → 启动
6. (如果 Owner 7 天不响应 → trigger_execution.status=expired, 不再提示)
```

### 6.5 旅程 E · IM 专家触发 skill（v0.4.2）

```
1. M4 阈值扫描器每天 02:00 跑一次（避开工作时间）
2. 扫描所有 IM signal: 检测到 user_alice 在 IM chat=后端群 的 K8s 主题
   累积了 22 条 signal 消息, 其中关联的 chapter approved 占比 0.85
3. 命中 priority=60 规则 → 写 trigger_execution { type=agent_skill }
4. 5 分钟撤回窗口 + Alice 个人通知 (因为 skill 会归属到她名下)
5. 调蒸馏接口 (复用 v0.3 §C.3 蒸馏管线), name_hint 由规则建议 ('k8s-troubleshooting-by-alice')
6. 生成 Skill draft, contributors=[alice]
7. Alice 审阅 → 接受 → status=active → 后续 LLM 生成自动注入
```

---

## 7. 功能需求

### 7.1 模块 AT-A · 触发规则引擎

> **目标**：5 种触发信号统一进入规则评估流程；每条规则只关心"是否命中"，命中后调用统一的 `dispatch_generation()`。

#### AT-A.1 规则定义结构

```python
@dataclass
class TriggerRule:
    id: str
    project_id: str | None  # None = 实例级默认规则
    name: str
    priority: int                # 0-100
    mode: Literal['cron', 'event', 'threshold', 'mention']
    asset_type: AssetType        # 命中后产生什么类型
    enabled: bool
    cooldown_seconds: int        # 默认 3600
    daily_cap: int               # 默认 5
    # 各 mode 专属字段
    cron_expr: str | None
    event_match: dict | None    # JSON: { event_type, label_in, file_glob, ... }
    threshold_spec: dict | None # JSON: { metric, comparator, value, window }
    # 配置元数据
    description: str
    created_by: str
    config: dict                 # 可扩展的 builder 配置
```

#### AT-A.2 评估 AC

```gherkin
功能: 规则评估器

场景: 多规则同时命中, 取最高 priority
  Given 项目 X 有两条 enabled rule:
    - r1: priority=85, event=PR merged with label "architecture-decision"
    - r2: priority=90, event=PR merged with file_glob "docs/design/**"
  When GitHub webhook 推来一个 PR merged 事件
    - labels: ["architecture-decision"]
    - files: ["docs/design/clickhouse.md", "src/db/migration.sql"]
  Then 引擎评估: r1 命中, r2 命中
  And 最终选 r2 (priority 90 > 85)
  And 写 trigger_execution { rule_id=r2, dropped_rules=[r1] }

场景: 在 cooldown 期内的规则被跳过
  Given rule r1 上次 fire 时间是 30 分钟前, cooldown=3600
  When 事件再次到达且命中 r1
  Then 写 trigger_execution { rule_id=r1, status=skipped, reason=cooldown }
  And 不调 LLM, 不创建 asset

场景: 当日同类型已达上限
  Given 当天该项目已经自动生成了 5 份 incident (daily_cap=5)
  When 又一个 incident 事件到达
  Then 写 trigger_execution { status=skipped, reason=daily_cap_reached }
  And 通知 Owner: "今天 incident 自动复盘已达上限, 请人工补"
```

### 7.2 模块 AT-B · 类型路由（可解释性）

> **目标**：每份自动生成的 asset 都能告诉用户"为什么被自动生成 / 为什么是这个类型"——满足要素 #34。

#### AT-B.1 trigger_meta 必填字段

每份通过 v0.4 自动生成的 asset 都必须有 `asset.trigger_meta`：

```json
{
  "trigger_mode": "event",
  "rule_id": "github-pr-architecture",
  "rule_name": "PR 含 architecture-decision label → ADR",
  "signal": {
    "type": "github_webhook",
    "event_id": "pr_merged_1234",
    "summary": "PR #1234 merged with label architecture-decision"
  },
  "confidence": 1.0,
  "fired_at": "2026-05-22T09:05:00Z",
  "dropped_rules": []
}
```

#### AT-B.2 类型路由可解释 UI（要素 #34）

文档详情页（DocumentPage）顶部加一个"为什么自动生成"展开卡，仅当 `asset.trigger_meta != null` 时显示：

```
🤖 自动生成 · 由规则 [PR 含 architecture-decision] 触发
   信号: PR #1234 (5/22 08:55 merged by alice)
   confidence: 1.0
   [查看完整审计] [报告误触发]
```

### 7.3 模块 AT-C · 调度器（APScheduler 接入）

> **目标**：所有定时任务（M2 cron + M4 阈值轮询）由统一的 APScheduler 调度。

#### AT-C.1 调度任务清单

| Job | 触发 | 执行内容 |
| --- | --- | --- |
| `cron_evaluator` | 每分钟 | 扫所有 enabled 且 mode=cron 的 rule，跑 cron_expr 判断是否到点 |
| `threshold_scanner` | 每 15 分钟 | 扫所有 enabled 且 mode=threshold 的 rule，跑数据库 query 判断阈值 |
| `skill_evolve_checker` | 每天 03:00 | 跑 `should_evolve()` 检查，触发自进化 |
| `quota_resetter` | 每月 1 日 00:00 | 重置项目月配额计数 |
| `cleanup_audit_log` | 每天 04:00 | 清理 ≥ 90 天的 trigger_execution（保留 audit_log） |
| `withdraw_window_resolver` | 每 30 秒 | 扫 status=scheduled 且 fire_at ≤ now 的 trigger_execution → 实际调 LLM |

#### AT-C.2 多实例考虑

**v0.4**：单实例 + AsyncIOScheduler。多实例时（v0.5+）切到 PostgreSQL JobStore，避免重复触发。

```python
# v0.4 默认配置
scheduler = AsyncIOScheduler(
    jobstores={'default': MemoryJobStore()},
    timezone='Asia/Shanghai',
    job_defaults={'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 300},
)
```

### 7.4 模块 AT-D · 配置面板（UI）

> **目标**：用户能在项目设置里看到所有触发规则，启停 / 调阈值。

#### AT-D.1 入口与路径

- 路径: `/projects/:id/settings?tab=auto-triggers`
- 入口: 项目设置左侧新增"自动触发"Tab（与"成员 / 数据源 / 出域"并列）

#### AT-D.2 列表视图（v0.4.0 只读 + 启停）

每条规则一行：

| 列 | 示例 |
| --- | --- |
| 状态 | ✅ 启用 / ⏸ 暂停 |
| 名称 | "周一 09:00 自动周报" |
| 模式 | M2 定时 |
| 触发条件 | cron `0 9 * * 1` 且上周 events ≥ 30 |
| 产出类型 | weekly_report |
| 最近触发 | 2 天前 ✓ |
| 30 天产出 | 4 份 |
| 操作 | [切换启停] [详情] |

#### AT-D.3 详情抽屉（v0.4.0）

点"详情"打开右侧抽屉：
- 描述（规则原理）
- 触发条件（JSON readonly）
- 频率限制配置（cooldown / daily_cap，readonly v0.4.0）
- 触发历史（最近 20 次 trigger_execution）
- 启停操作

#### AT-D.4 编辑器（v0.4.3 完整版）

基于 builder 模板，不开放自由 DSL：

```
+ 新建规则
  类型 (mode): [定时 ▼]
  触发条件 (builder):
    - [周/月/天/cron 表达式]
    - cron: [0 9 * * 1] (周一 9 点)
    - 附加条件: 上周 events 数 ≥ [30]
  产出: [weekly_report ▼]
  优先级: [50]
  Cooldown: [3600 秒]
  每日上限: [5]
```

#### AT-D.5 首次启用引导（要素 #35）

第一次访问 `?tab=auto-triggers` 时弹引导：

```
✨ 启用自动触发？
TokenKnows 可以基于研发过程自动产出文档,
我们为你预选了 4 条最常用规则:

[✓] 周一 09:00 自动周报         · weekly_report
[✓] PR 标 architecture → ADR     · adr
[✓] Issue 标 incident → 复盘     · incident
[ ] 累积 50 章 → 自动书籍 (token 用量大, 默认关)

[启用选中]  [跳过, 我自己配]
```

### 7.5 模块 AT-E · 审计 + 撤回 + 回滚

#### AT-E.1 5 分钟撤回窗口（AT-4）

每次规则命中 → 写 trigger_execution { status=scheduled, fire_at=now+5min } → SSE 推通知 → 用户可点"取消" → 改 trigger_execution.status=canceled，不再 fire。

#### AT-E.2 自动生成历史时间轴（要素 #31）

`/projects/:id/settings?tab=auto-triggers&view=history`：

```
今天
  09:05  [ADR] PR #1234 触发 · 草稿 #45 (待审)        [查看] [报告误触发]
昨天
  09:00  [周报] cron Week 21 · 已发布 #44             [查看]
3 天前
  14:23  [incident] Issue #88 触发 · 草稿 #43 (已归档) [查看]
  02:11  [跳过] PR #1233 触发 ADR (cooldown, 距上次 30 分钟)
```

#### AT-E.3 一键归档

误触发的 asset，用户在文档详情页可点"归档"按钮：
- asset.status = archived
- trigger_execution 上标 user_flagged_false_positive = true
- 触发"误触发学习"反馈：累积 5 个同规则的误触发 → UI 提示 Owner "是否需要调整这条规则的阈值？"

---

## 8. 数据模型

> 复用现有 user / project / asset / event 表，新增 3 张 v0.4 专属表。

### 8.1 trigger_rule（触发规则定义）

```sql
CREATE TABLE trigger_rule (
  id            UUID PRIMARY KEY,
  project_id    UUID REFERENCES project(id),  -- NULL = 实例级默认规则
  name          TEXT NOT NULL,
  description   TEXT,
  priority      INT NOT NULL DEFAULT 50,      -- 0-100
  mode          TEXT NOT NULL,                -- 'cron' | 'event' | 'threshold' | 'mention'
  asset_type    TEXT NOT NULL,                -- 命中后产出的 asset 类型
  enabled       BOOLEAN NOT NULL DEFAULT true,
  -- 频率限制
  cooldown_seconds INT NOT NULL DEFAULT 3600,
  daily_cap     INT NOT NULL DEFAULT 5,
  -- 各 mode 专属配置 (JSONB 留扩展空间)
  cron_expr     TEXT,                          -- mode=cron 时必填
  event_match   JSONB,                         -- mode=event 时必填
  threshold_spec JSONB,                        -- mode=threshold 时必填
  -- 元数据
  created_by    UUID NOT NULL REFERENCES "user"(id),
  config        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- 索引
  UNIQUE (project_id, name)
);

CREATE INDEX trigger_rule_enabled_idx ON trigger_rule(enabled, mode) WHERE enabled = true;
CREATE INDEX trigger_rule_project_idx ON trigger_rule(project_id);
```

### 8.2 trigger_execution（执行历史）

```sql
CREATE TABLE trigger_execution (
  id            UUID PRIMARY KEY,
  rule_id       UUID NOT NULL REFERENCES trigger_rule(id),
  project_id    UUID NOT NULL REFERENCES project(id),
  -- 状态机
  status        TEXT NOT NULL,
  -- 'scheduled' | 'fired' | 'canceled' | 'skipped' | 'failed' | 'expired'
  fire_at       TIMESTAMPTZ NOT NULL,         -- 计划触发时间 (含 5 分钟撤回窗口)
  fired_at      TIMESTAMPTZ,                  -- 实际触发时间
  -- 信号溯源
  signal        JSONB NOT NULL,
  -- 例: { type: 'github_webhook', event_id: 'pr_1234', summary: '...' }
  evaluation    JSONB,
  -- 评估过程: { matched: true, dropped_rules: [...], confidence: 1.0 }
  -- 结果
  asset_id      UUID REFERENCES asset(id),    -- 成功后关联生成的 asset
  skip_reason   TEXT,                         -- 'cooldown' | 'daily_cap' | 'low_confidence' | 'canceled_by_user'
  error_message TEXT,                         -- status=failed 时记错误
  -- 用户反馈
  user_canceled BOOLEAN DEFAULT false,
  user_flagged_false_positive BOOLEAN DEFAULT false,
  -- 时间
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX trigger_exec_status_fire_at_idx ON trigger_execution(status, fire_at)
  WHERE status = 'scheduled';
CREATE INDEX trigger_exec_project_created_idx ON trigger_execution(project_id, created_at DESC);
CREATE INDEX trigger_exec_rule_created_idx ON trigger_execution(rule_id, created_at DESC);
```

### 8.3 generation_quota（资源配额，每月一行）

```sql
CREATE TABLE generation_quota (
  id            UUID PRIMARY KEY,
  project_id    UUID NOT NULL REFERENCES project(id),
  year_month    TEXT NOT NULL,                -- '2026-05'
  -- 限额（管理员配置）
  monthly_token_limit  BIGINT NOT NULL,       -- 例如 5_000_000
  daily_auto_gen_limit INT NOT NULL DEFAULT 20,
  -- 用量计数
  tokens_used   BIGINT NOT NULL DEFAULT 0,
  auto_gen_count INT NOT NULL DEFAULT 0,
  -- 状态
  is_throttled  BOOLEAN NOT NULL DEFAULT false, -- 超额自动设置 true
  throttled_at  TIMESTAMPTZ,
  -- 时间
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- 索引
  UNIQUE (project_id, year_month)
);
```

### 8.4 与现有 Asset Schema 桥接

不新建表，给 `asset` 表加字段：

```sql
ALTER TABLE asset ADD COLUMN trigger_meta JSONB;
-- 例: { trigger_mode, rule_id, rule_name, signal: {...}, confidence, fired_at, ... }
ALTER TABLE asset ADD COLUMN trigger_execution_id UUID REFERENCES trigger_execution(id);
```

asset.trigger_meta 不为空时 → UI 显示"自动触发"徽标（要素 #33）+ 可解释卡（AT-B.2）。

---

## 9. 技术架构

### 9.1 整体拓扑

```
┌────────────────────────────────────────────────────────────────┐
│                       TokenKnows 主进程                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐         │
│  │  API     │  │  Generation  │  │  LLM Gateway     │         │
│  │  FastAPI │  │  Pipeline    │  │  (三层出域门禁)   │         │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘         │
│       │               │                   │                    │
│       └───────────────┴───────────────────┘                    │
│                       ▲                                         │
│       ┌───────────────┴──────────────┐                         │
│       │  Auto-Trigger Module (v0.4) │  ← 新增                  │
│       │  ┌──────────────────────┐   │                         │
│       │  │  APScheduler          │   │                         │
│       │  │  ├ cron_evaluator     │   │                         │
│       │  │  ├ threshold_scanner  │   │                         │
│       │  │  ├ withdraw_resolver  │   │                         │
│       │  │  └ ...                │   │                         │
│       │  └──────────┬───────────┘   │                         │
│       │             │                │                         │
│       │  ┌──────────▼───────────┐   │                         │
│       │  │  RuleEvaluator        │   │                         │
│       │  └──────────┬───────────┘   │                         │
│       │             │                │                         │
│       │  ┌──────────▼───────────┐   │                         │
│       │  │  QuotaGuard           │   │                         │
│       │  └──────────┬───────────┘   │                         │
│       │             │                │                         │
│       │  ┌──────────▼───────────┐   │                         │
│       │  │  TriggerDispatcher    │ → → 调 Generation Pipeline │
│       │  └──────────────────────┘   │                         │
│       └──────────────────────────────┘                         │
└────────────────────────────────────────────────────────────────┘
                       ▲
        ┌──────────────┴───────────────┐
        │   外部信号源（事件源）         │
        ▼                              ▼
┌──────────────┐               ┌──────────────┐
│  GitHub      │               │  IM Connector │
│  Webhook     │               │  (v0.3)       │
└──────────────┘               └──────────────┘
```

### 9.2 调度器选型对比

| 选项 | 优势 | 劣势 | v0.4 决策 |
| --- | --- | --- | --- |
| **APScheduler 4.x** | in-process AsyncIO，零额外依赖；嵌入 FastAPI；JobStore 可换 | 单实例限制（v0.5 切 Postgres JobStore） | ✅ 选这个 |
| Celery Beat | 工业级、多实例、动态 | 需要 Redis + Worker 进程，部署复杂度++ | ❌ 重，留 v0.6 |
| 自写 asyncio loop | 完全可控 | 重复造轮子、cron 表达式解析、错误恢复都得自己写 | ❌ |
| cron + systemd | 简单 | 与 FastAPI 进程脱节、共享状态难 | ❌ |

### 9.3 APScheduler 接入

```python
# code/tokenknows-api/app/services/auto_trigger/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """在 FastAPI lifespan 启动时调用。"""
    global scheduler
    scheduler = AsyncIOScheduler(
        jobstores={'default': MemoryJobStore()},
        timezone='Asia/Shanghai',
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 300,
        },
    )

    # 固定 jobs (与 trigger_rule 表无关, 由代码直接挂)
    scheduler.add_job(
        cron_evaluator, IntervalTrigger(minutes=1),
        id='cron_evaluator', replace_existing=True,
    )
    scheduler.add_job(
        threshold_scanner, IntervalTrigger(minutes=15),
        id='threshold_scanner', replace_existing=True,
    )
    scheduler.add_job(
        withdraw_window_resolver, IntervalTrigger(seconds=30),
        id='withdraw_resolver', replace_existing=True,
    )
    scheduler.add_job(
        skill_evolve_checker, CronTrigger(hour=3, minute=0),
        id='skill_evolve', replace_existing=True,
    )
    scheduler.add_job(
        quota_resetter, CronTrigger(day=1, hour=0, minute=0),
        id='quota_reset', replace_existing=True,
    )

    scheduler.start()
    return scheduler
```

### 9.4 与 LLM Gateway 协作

v0.4 自动触发**不绕过**任何 LLM Gateway 安全机制：

1. **出域门禁**：自动触发 → QuotaGuard → LLM Gateway → 三层出域开关（实例 / 项目 / task）逐层校验
2. **路由**：复用现有 task → provider 路由配置；自动周报走 `TASK_WEEKLY_REPORT_PROVIDER`
3. **审计**：每次自动触发的 LLM 调用都正常进 egress_log，trigger_execution_id 作为关联字段
4. **fallback**：LLM provider 失败 → 重试 1 次 → 失败 → 写 trigger_execution status=failed，不创建 asset，给 Owner 告警

### 9.5 与 Reviewer 流程协作

自动生成的 asset 直接进入审批流（PRD §4.3）：

```
auto-trigger (v0.4)
   ↓
asset { status: 'draft', trigger_meta: {...} }
   ↓
（用户编辑可选）→ 提交审批
   ↓
Reviewer 审批（与手动生成完全相同的流程）
   ↓
approved → publishable
```

**关键约束**：
- 自动生成 asset 在 7 天内未被 Editor 触碰 → 自动归档（status=archived），减小审批面板压力
- Reviewer 看到的"待审"面板，每份 asset 都有"手动 / 自动"标签，可分别过滤

### 9.6 部署形态

无新增容器。APScheduler 嵌入 FastAPI 主进程，与 v0.3 IM 的 retention/token_refresher 后台 task 同进程并存。

`main.py` lifespan 函数加：

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ... 现有 IM bg tasks ...

    # v0.4 · 启动 Auto-Trigger Scheduler
    if not _is_test_mode():
        scheduler = start_scheduler()
        logger.info("auto_trigger_scheduler_started", job_count=len(scheduler.get_jobs()))

    yield

    if not _is_test_mode():
        scheduler.shutdown(wait=False)
        logger.info("auto_trigger_scheduler_stopped")
```

---

## 10. API 设计

> 沿用 MVP TDD §6.1 的 REST 风格，新增 `/auto-triggers/*` 命名空间。

### 10.1 规则管理

```
POST   /api/projects/{pid}/auto-triggers/rules
       创建规则
       body: { name, priority, mode, asset_type, ... }
       resp: TriggerRule

GET    /api/projects/{pid}/auto-triggers/rules
       列出所有规则（含默认 + 自定义）
       query: ?enabled=true|false&mode=cron|event|threshold

PATCH  /api/projects/{pid}/auto-triggers/rules/{rid}
       修改规则（含启停）
       body: { enabled?, priority?, cooldown_seconds?, ... }

DELETE /api/projects/{pid}/auto-triggers/rules/{rid}
```

### 10.2 执行历史

```
GET    /api/projects/{pid}/auto-triggers/executions
       触发历史时间轴
       query: ?since=...&status=fired|skipped|canceled|failed&rule_id=

GET    /api/projects/{pid}/auto-triggers/executions/{eid}
       单次执行详情（含信号 / 评估 / 结果）

POST   /api/projects/{pid}/auto-triggers/executions/{eid}/cancel
       撤回（仅 status=scheduled 时允许）

POST   /api/projects/{pid}/auto-triggers/executions/{eid}/flag-false-positive
       报告误触发
```

### 10.3 配额管理

```
GET    /api/projects/{pid}/auto-triggers/quota?month=2026-05
       当月用量 + 限额
       resp: { monthly_token_limit, tokens_used, daily_auto_gen_limit, auto_gen_count, is_throttled }

PATCH  /api/projects/{pid}/auto-triggers/quota
       仅 Owner / 实例管理员可调
       body: { monthly_token_limit, daily_auto_gen_limit }
```

### 10.4 引导（首次启用）

```
GET    /api/projects/{pid}/auto-triggers/onboarding
       返回 4 条预置规则的预览
       resp: { default_rules: [...] }

POST   /api/projects/{pid}/auto-triggers/onboarding
       一键启用选中的预置规则
       body: { enabled_rule_ids: [...] }
```

### 10.5 SSE 推送

复用 MVP §6.2 SSE 通道，新增事件类型：

- `auto_trigger.scheduled`（5 分钟撤回窗口开始）
- `auto_trigger.fired`（实际产出 asset）
- `auto_trigger.canceled`
- `auto_trigger.skipped`
- `auto_trigger.failed`
- `auto_trigger.quota_warning`（用量到 80%）
- `auto_trigger.quota_exceeded`（用量到 100%，所有规则暂停）

---

## 11. 安全实现

### 11.1 权限矩阵

| 操作 | 角色要求 |
| --- | --- |
| 查看规则列表 | 项目任意成员 |
| 启停规则 | Owner / Editor |
| 创建/修改/删除规则 | 仅 Owner |
| 撤回 scheduled 执行 | Owner / Editor |
| 报告误触发 | Owner / Editor / Reviewer |
| 改月配额 | 仅 Owner（受实例管理员上限约束）|
| 实例级默认规则 | 仅实例管理员 |

### 11.2 频率限制（防止规则风暴）

三层防护：

1. **规则级 cooldown**：每条 rule 上的 cooldown_seconds（默认 3600）
2. **类型级 daily_cap**：同类型每天最多 N 份（默认 5）
3. **项目级月配额**：硬上限，超额所有规则 paused（AT-7）

**新增 Redis key**：`auto_trigger:rule:{rule_id}:last_fire_at` TTL = cooldown_seconds，原子性 `SET NX EX` 确认下一次能否 fire。

### 11.3 资源配额（每月 LLM token 上限）

**配额仪表盘（要素 #32）**显示：

| 指标 | 示例 |
| --- | --- |
| 本月已用 / 上限 | 1.2M / 5M tokens |
| 进度条 | ████████░░ 24% |
| 月剩余天数 | 9 天 |
| 预估超额风险 | 低（按当前速度月底 3.6M）|
| 自动暂停阈值 | 100%（超过自动暂停所有 enabled rule） |
| 历史月用量 | 折线图 |

**超额逻辑**：
- 80% → 给 Owner 邮件预警
- 100% → 自动设 generation_quota.is_throttled=true → 所有 enabled rule 跳过新触发；UI 显著告警
- 月初 1 日 00:00 → quota_resetter 重置计数

### 11.4 审计与回滚

每次 trigger_execution 进入 fired 状态前，**先在 generation_audit_log 写一条预记录**（复用 MVP TDD §5.4 audit_log 表，新增 event_type）：

| event_type | 触发时机 |
| --- | --- |
| `auto_trigger.rule.created` | 创建规则 |
| `auto_trigger.rule.toggled` | 启停切换 |
| `auto_trigger.rule.updated` | 修改 |
| `auto_trigger.execution.fired` | 真实调 LLM 之前 |
| `auto_trigger.execution.canceled` | 用户取消 |
| `auto_trigger.quota.exceeded` | 触发配额限额 |
| `auto_trigger.false_positive.reported` | 用户报告误触发 |

**回滚**：用户在执行历史里点"归档"任一自动生成的 asset → asset.status=archived + audit_log 记录 user_id 与时间。

---

## 12. 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- | --- |
| R1 | LLM 账单失控 | 中 | 高 | 月配额硬墙 + 80% 预警 + 类型 daily_cap |
| R2 | 规则风暴（如 PR webhook 风暴）| 中 | 高 | rule cooldown + Redis 原子锁 |
| R3 | 误触发淹没 Reviewer 审批面板 | 中 | 中 | 7 天未触碰自动归档 + 误触发反馈学习 |
| R4 | 类型路由判错（如把周报判成 incident）| 低 | 中 | 规则优先级清晰 + 可解释卡 + 用户可关单条规则 |
| R5 | APScheduler 单实例瓶颈 | 低 | 中 | v0.4 单实例；v0.5 切 PostgreSQL JobStore |
| R6 | 撤回窗口期内系统重启导致丢任务 | 低 | 低 | trigger_execution 持久化 → withdraw_resolver 启动时恢复扫描 |
| R7 | GitHub webhook 重放攻击 | 低 | 中 | webhook 签名校验 + nonce + 时间戳（5 分钟）|
| R8 | 用户改规则但忘记关 cooldown 导致触发风暴 | 中 | 中 | 编辑器强制 cooldown ≥ 60s；规则变更前预估每日产出量 |
| R9 | 跨时区 cron 触发歧义 | 中 | 低 | 全局 timezone='Asia/Shanghai'；UI 显示用户本地时间 |
| R10 | 自动生成的 incident 复盘内容不实（LLM 幻觉）| 中 | 高 | Reviewer 必经；模板强制证据链；用户可标 false_positive |
| R11 | Quota 计数与实际 LLM 调用不同步 | 中 | 中 | 每次 LLM 调用前预扣 token、调用后对账修正；定期校准 |
| R12 | 用户没看通知就开始自动生成 | 低 | 低 | 5 分钟撤回窗口 + UI 通知聚合 + 可在设置里调撤回窗口长度（默认 5min）|

---

## 13. 发布里程碑

### 13.1 v0.4.0 · 定时触发 + 撤回窗口（核心 MVP）

**范围：**
- APScheduler 接入 + lifespan 集成
- 数据库 migration（3 张新表 + asset patch）
- trigger_rule / trigger_execution CRUD
- cron_evaluator + withdraw_window_resolver
- 4 条预置规则（周报 / ADR / incident / skill）注册到默认表
- UI：项目设置"自动触发"Tab 只读列表 + 启停 toggle + 引导向导（要素 #35）
- 5 分钟撤回窗口 + SSE 通知卡（要素 #30）
- asset 上"自动触发"徽标（要素 #33）+ 可解释卡（要素 #34）

**预计周期**：2 sprint（4 周）

**验收 AC：**
- 真实试点项目 30 天内：自动产出 ≥ 4 份周报 + ≥ 1 份 ADR + ≥ 1 份 incident，且 0 次误触发账单异常
- 撤回窗口实测：用户取消率 < 10%（说明命中精度可接受）
- 调度器在 1000+ 次任务执行下无丢失 / 无重复

### 13.2 v0.4.1 · 事件触发（GitHub Webhook）

**范围：**
- `/api/webhooks/github` 入口（沿用 v0.3 IM webhook 安全机制）
- event_match 规则评估器
- GitHub PR / Issue 事件归一化到 events 表
- 默认 2 条 event 规则启用（PR architecture-decision → ADR / Issue incident → 复盘）

**预计周期**：+2 sprint

### 13.3 v0.4.2 · 阈值触发 + Skill 自动蒸馏

**范围：**
- threshold_scanner（每 15 分钟扫）
- 默认 2 条阈值规则（50 章 → book / 20 IM signal → skill）
- skill_evolve_checker 每天 03:00 跑（自进化）

**预计周期**：+1 sprint

### 13.4 v0.4.3 · UI 配置面板完整版

**范围：**
- 规则 builder 编辑器（非 DSL）
- 触发历史时间轴（要素 #31）
- 误触发反馈学习

**预计周期**：+1 sprint

### 13.5 v0.4.4 · 配额仪表盘 + 告警

**范围：**
- generation_quota 表 + UI 仪表盘（要素 #32）
- 月初重置 cron
- 80% 邮件预警 + 100% 自动暂停

**预计周期**：+1 sprint

---

## 14. 开放问题（需用户决策）

| # | 问题 | 选项 | 建议 |
| --- | --- | --- | --- |
| Q1 | 5 分钟撤回窗口长度是否可配？ | 固定 5 min / 用户可调 1-15 min / 取消功能 | 用户可调（默认 5 min，最小 1 min）|
| Q2 | 自动归档"7 天未触碰" 这个阈值合理吗？ | 3 天 / 7 天 / 14 天 / 不归档 | 7 天（与企业 OKR 周期对齐）|
| Q3 | 月配额默认值？ | 1M / 5M / 10M / 无默认 | 5M token/月（覆盖 ~50 份长文档）|
| Q4 | book 类型默认勾选启用吗？ | 默认勾 / 默认不勾 | 默认不勾（token 用量大）|
| Q5 | Skill 自动蒸馏需要 Alice 个人确认吗？ | 必须 / 可选 / 不需要 | 必须（contributor 个人权）|
| Q6 | 实例级默认规则能否被项目级覆盖？ | 是 / 否 | 是（项目级优先，实例级兜底）|
| Q7 | 配额仪表盘是否对所有项目成员可见？ | 全可见 / 仅 Owner / 仅管理员 | Owner 可见 + 实例管理员可见所有项目 |
| Q8 | Skill 自进化检查是每天一次还是每周？ | 每天 / 每周 / 实时 | 每天 03:00 |

---

## 15. 附录

### 附录 A · 规则模板（预置 4 条 + 扩展）

#### A.1 周一定时周报

```json
{
  "name": "周一 09:00 自动周报",
  "mode": "cron",
  "asset_type": "weekly_report",
  "priority": 50,
  "cooldown_seconds": 86400,
  "daily_cap": 1,
  "cron_expr": "0 9 * * 1",
  "extra_condition": {
    "metric": "events_last_7d",
    "comparator": ">=",
    "value": 30
  },
  "enabled": true
}
```

#### A.2 PR 含 architecture-decision → ADR

```json
{
  "name": "PR 标 architecture → ADR",
  "mode": "event",
  "asset_type": "adr",
  "priority": 85,
  "cooldown_seconds": 3600,
  "daily_cap": 5,
  "event_match": {
    "event_type": "github_pr_merged",
    "label_any": ["architecture-decision", "adr"]
  },
  "enabled": true
}
```

#### A.3 Issue 标 incident → 复盘

```json
{
  "name": "Issue incident → 复盘",
  "mode": "event",
  "asset_type": "incident",
  "priority": 100,
  "cooldown_seconds": 1800,
  "daily_cap": 5,
  "event_match": {
    "event_type": "github_issue_opened",
    "label_any": ["incident", "outage", "production-issue"]
  },
  "enabled": true
}
```

#### A.4 累积 50 章 → book（默认关）

```json
{
  "name": "累积 50 章 approved → 自动书籍",
  "mode": "threshold",
  "asset_type": "book",
  "priority": 70,
  "cooldown_seconds": 604800,
  "daily_cap": 1,
  "threshold_spec": {
    "metric": "approved_chapters_total",
    "comparator": ">=",
    "value": 50,
    "and_not_exists_asset_of_type": "book"
  },
  "enabled": false
}
```

### 附录 B · 性能基线（v0.4 假设值，灰度后校准）

| 指标 | 目标 |
| --- | --- |
| cron_evaluator 单次扫描耗时 | < 200ms（覆盖 100 条 rule）|
| threshold_scanner 单次扫描耗时 | < 1s（含 SQL aggregation）|
| 规则评估到 LLM 调用延迟 P95 | < 6 min（含 5 min 撤回窗口）|
| 单条 rule 命中 → trigger_execution 写入延迟 | < 50ms |
| 配额仪表盘加载延迟 | < 500ms |

### 附录 C · 监控指标（Prometheus）

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `auto_trigger_rule_evaluations_total{mode}` | counter | 规则评估次数 |
| `auto_trigger_executions_total{status, rule_id}` | counter | 执行结果分布 |
| `auto_trigger_scheduled_pending_count` | gauge | 撤回窗口期内待 fire 任务数 |
| `auto_trigger_quota_usage_ratio{project_id}` | gauge | 月配额用量比 |
| `auto_trigger_dispatch_duration_seconds` | histogram | 从命中到 LLM 调用结束的总耗时 |
| `auto_trigger_false_positive_rate{rule_id}` | gauge | 30 天内被标 false_positive 比例 |

### 附录 D · 与 v0.3 IM 的协同点

| 点 | 描述 |
| --- | --- |
| IM SignalGate → 阈值触发 | v0.3 SignalGate 标记的 signal 消息，被 v0.4 threshold_scanner 用作 skill 自动蒸馏的输入 |
| @ 机器人按需蒸馏 | v0.3.4 计划的"@ 机器人 /distill" 复用 v0.4 dispatch_generation 主流程 |
| IM Connection 状态变更 → 触发欢迎周报 | 用户首次接入 IM 7 天后自动产出"上周 IM 数据初探"周报 |

---

## 16. 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.4-draft.1 | 2026-05-22 | 初稿；含 5 种触发模式 + 类型路由表 + APScheduler 架构 + UI 配置面板 + 配额机制 |

---

**Sources / 参考：**
- APScheduler 4.x 文档 · https://apscheduler.readthedocs.io/
- GitHub Webhooks · https://docs.github.com/en/webhooks
- PRD MVP §3.1 / §4.2 / §5.3 价值主张与决策表
- v0.3 IM 提案 §7.2 SignalGate（为 skill 自动蒸馏提供信号源）
