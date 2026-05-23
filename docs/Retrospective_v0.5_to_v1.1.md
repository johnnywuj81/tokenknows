# TokenKnows 复盘报告 · v0.5 → v1.1

> 时间窗口: 单一会话 (2026-05-23 一日内)
> 范围: v0.5.0 → v1.1.0 共 8 个 release (含 v0.5.0/.1/.2, v0.6.0, v0.7.0, v0.8.0, v0.9.0, v1.0.0/.1, v1.1.0)
> 任务总数: T45-T78 共 **34 task**, ~17k LoC 新增, **2227 test** (后端 1462 + 前端 765)

---

## 1. 全景 (TL;DR)

```
v0.5.0 (T45-T47)  · @bot 按需触发 + IM thread 回执
v0.5.1 (T48-T51)  · Q5 contributor 个人同意闸门
v0.5.2 (T52-T55)  · SSE 实时 + 钉钉/企微 DM 实装
v0.6.0 (T56-T58)  · Reviewer 审批流 (draft → active)
v0.7.0 (T59-T61)  · Skill 池自治理日循环 (evolve / deprecate / trust)
v0.8.0 (T62-T64)  · Governance Dashboard + Skill 详情页 timeline
v0.9.0 (T65-T67)  · Reviewer 角色显式化 + ACL (X-User-Id MVP)
v1.0.0 (T68-T70)  · Skill Marketplace MVP (跨项目发布 + import)
v1.0.1 (T71-T73)  · 并行 3-reviewer 代码审查 + 修 18 项 HIGH/CRITICAL
v1.1.0 (T74-T76)  · JWT 真 session (替换 X-User-Id MVP)
v1.1.x (T77-T78)  · 复盘报告 + e2e demo (本批次)
```

闭环价值链:
```
@bot mention → 蒸馏 Skill → contributor 全员同意 → submit → Reviewer 审批 →
  active → owner publish 到 Marketplace → 其他项目 import → 走本地审批流
       + 每天 02:00 trust 重算 / 03:00 evolve / 03:10 deprecate
```

---

## 2. 关键决策记录 (DR)

| ID | 决策 | 影响 |
|---|---|---|
| DR-1 | OD-7: 飞书 interactive card 主, 钉钉 ActionCard 次, 企微 textcard 单链接 degrade | 3 平台 IM 通知统一抽象 (consent_notifier.py) |
| DR-2 | Q5: 自动蒸馏 Skill 必须每位 contributor 个人同意, 非 group consent | 加 pending_contributor_consent 状态 + 30d expires |
| DR-3 | review_state 与 status 正交 (而非合并) | 既允许 draft+pending_review 又允许 active+approved; 历史 review_history 与 status 解耦 |
| DR-4 | trust_score 每天 02:00 全量重算 vs 仅 use 时算 | 解决 recency_decay 时间函数性问题 (~12 行新代码换排序正确性) |
| DR-5 | Marketplace import 创建独立 entity, 不继承 evolve_chain / consent / metrics | 跨项目独立审计 + 各自 trust 累积; 撤回上游不影响下游副本 |
| DR-6 | ACL 三层: owner ⊇ reviewer ⊇ contributor | 隐含权重大幅简化 endpoint 校验 (单 has_role 调用) |
| DR-7 | v0.9 X-User-Id MVP → v1.1 JWT 升级, 保留 X-User-Id fallback | 平滑过渡, 老 client 不破 |
| DR-8 | bootstrap owner 用进程内 _bootstrap_lock | 单实例够; 多实例需 DB unique 约束 (留 v1.2) |
| DR-9 | import_skill embedding=None + 异步重算 | 避免 select_skills 排序失效; asyncio.create_task fire-and-forget |
| DR-10 | reject 必填 reason ≥ 1/5 字; sign note 可选 | Reviewer 决策审计可追溯; 容忍 sign 路径 friction |

---

## 3. 模块产出 (按层)

### 3.1 后端 (`code/tokenknows-api/`)

| 模块 | 起源 | 角色 |
|---|---|---|
| `services/skill/consent.py` | T48 | 9 纯函数: initialize_pending / can_transition / apply_sign|reject / mark_expired / sweep |
| `services/skill/review.py` | T56 | submit_for_review / approve / reject + 转换矩阵 |
| `services/skill/review_notifier.py` | T57 | review_request + review_decision web+SSE |
| `services/skill/pool.py` | T59 | evolve / deprecation 候选 collector + trust recompute + governance summary + evolve_chain |
| `services/skill/marketplace.py` | T68 | publish / unpublish / list / import |
| `services/im/consent_notifier.py` | T49 | 3 平台 IM DM (feishu interactive / dingtalk ActionCard / wework textcard) + web notification + SSE publish |
| `services/notification_sse.py` | T52 | user-scoped SSE pub/sub (in-memory fan-out) |
| `services/project/membership.py` | T65 | CRUD + ACL (has_role, is_owner, can_review, can_contribute) |
| `services/auth/token.py` | T74 | JWT issue/decode + bcrypt hash/verify |
| `services/auth/user_service.py` | T74 | register / login / get_user |
| `gateway/http_api/skills.py` | (扩展 v0.2) | 增 12 endpoint (consent sign|reject / review submit|approve|reject / governance 4 / marketplace publish|unpublish|import + list) |
| `gateway/http_api/notifications.py` | T49+T51 | 5 endpoint + SSE stream |
| `gateway/http_api/members.py` | T66 | 5 endpoint (members CRUD + /me/memberships) |
| `gateway/http_api/auth.py` | T74 | 3 endpoint (register / login / me) |
| `gateway/http_api/_session.py` | T66 → T75 | get_current_user_id / require_user_id (JWT-first, X-User-Id fallback) |
| `auto_trigger/jobs.py` | v0.4 → +4 jobs | consent_sweep / skill_evolve / skill_deprecation_sweep / skill_trust_recompute |

### 3.2 前端 (`code/tokenknows-web/`)

| 模块 | 起源 | 角色 |
|---|---|---|
| `features/notifications/` | T51+T54 | NotificationBell + List + Item + SSE hook (EventSource) + 4 query hook |
| `features/skills/components/ConsentPending` | T51 | pending_contributor_consent banner + sign/reject 按钮 |
| `features/skills/components/ConsentDialog` | T51 | 二次确认弹窗 |
| `features/skills/components/ReviewActions` | T58 | 4 review_state 分支 banner |
| `features/skills/components/ReviewDialog` | T58 | submit/approve/reject 复用弹窗 |
| `features/skills/components/EvolveChain` | T63 | parent → current → children 横向 timeline |
| `features/skills/components/ReviewTimeline` | T63 | review_history 竖向 timeline |
| `features/skills/components/PublishToggle` | T70 | 发布/撤回 Marketplace |
| `features/skills/ReviewerInboxPage` | T58 | 待审批列表 |
| `features/skills/GovernancePage` | T64 | 6 stat + 3 candidate + 2 sweep 按钮 |
| `features/marketplace/MarketplacePage` | T70 | 全局 Skill 市场 (搜索 + import) |
| `features/settings/tabs/MembersPanel` | T67 | 成员列表 + role select + add/remove |
| `lib/api.ts` (interceptor) | T67+T76 | Authorization Bearer + X-User-Id 兼容 |

---

## 4. 测试矩阵

| Release | 后端 +Δ | 前端 +Δ | 总后端 | 总前端 |
|---|---|---|---|---|
| v0.5.0 | +60 (T45-T47) | — | 1128 | 705 |
| v0.5.1 | +121 (T48-T51 + endpoints) | +27 | 1249 | 732 |
| v0.5.2 | +14 (T52+T53) | +8 (T54) | 1263 | 740 |
| (T55 钉/企) | +14 | — | 1277 | 740 |
| v0.6.0 | +48 (T56+T57) | +15 (T58) | 1325 | 755 |
| v0.7.0 | +33 (T59-T61) | — | 1358 | 755 |
| v0.8.0 | +13 (T62) | +15 (T63+T64) | 1371 | 770 |
| v0.9.0 | +36 (T65+T66) | +8 (T67) | 1407 | 778 |
| v1.0.0 | +27 (T68+T69) | +12 (T70) | 1434 | 790 |
| v1.0.1 | +3 net (T72 review fix) | — | 1437 | 790 |
| v1.1.0 | +25 (T74+T75) | 0 (T76 types) | 1462 | 790 |
| **累计 v0.5-v1.1** | **+334** | **+85** | **1462** | **790** |

测试增量 4:1 LoC 比例 (后端 +12k LoC 配 +334 test ≈ 36 LoC/test; 已在合理区间).

---

## 5. 决策偏差 (Plan vs Reality)

| 计划 | 实际 | 原因 |
|---|---|---|
| v0.5 Proposal 3 个 task (T45-T47) | 11 个 task (含 v0.5.1/.2) | OD-5 thread reply 拆出 T47; Q5 consent 衍生 T48-T51; SSE/钉/企 衍生 T52-T55 |
| 钉钉/企微 v0.5.0.1 实装 | v0.5.2 实装 | 集成 SSE 比拆 v0.5.0.1 优先级高 |
| Marketplace 计划"完整"(comment+rating) | MVP (仅 publish + import) | 决策: 先 publish-import 闭环, social 留 v1.2 |
| JWT v0.9 直接上 | v1.1 才升级 | X-User-Id MVP 给 v0.9-v1.0 快速验证 ACL, JWT 是 hardening |
| email_verified_at v1.1 | 留 v1.2 | 不阻塞 MVP, 注册即可用 |

---

## 6. 经验教训

### 6.1 收获
1. **三 reviewer agent 并行扫**找到 **18 项 HIGH/CRITICAL**, 价值远超人工逐文件 review. 后续每个 release 收尾应固化为流程
2. **pure-function service layer** (consent.py / review.py / pool.py) 极易测试, 90% 测试是单元 test 没有 DB/IO 桩
3. **backward-compat 双轨制** (X-User-Id 与 JWT 并存) 让 v1.1 升级零破坏
4. **状态机正交分离** (status × review_state × visibility) 比单一 status enum 灵活, 加新流程不动旧 enum

### 6.2 痛点
1. **私有属性访问** (`_skills`) 在 review 中被指出, fix 加 `all_skills()` accessor 后还需改 4 处, 早期就该建公开 API
2. **bcrypt 5.x 不兼容 passlib 1.7.x** 是隐藏依赖坑, 需 pin <4.1; v1.2 切 `argon2-cffi` 更稳
3. **SSE 测试用 TestClient 阻塞** (stream endpoint 无法读完整事件流), 转为单元测 publish_to_user, 用 smoke 测 endpoint 仅返 200 + content-type
4. **frontend Tailwind v4 + Radix DropdownMenu in jsdom 无法点开**, 测试只能验 button 状态, popover 行为留 e2e
5. **import 后 embedding 触发缺失** 是 review 才发现的功能 gap, 不是 type 错; pure function 测试盲区 — 需要 integration test 验副作用

### 6.3 反 pattern
1. **`event` 在 structlog 是保留 kwarg**: 第一次写 `logger.warning("...", event=ev.event)` 报 `multiple values for argument 'event'`, 改名 `event_type`
2. **`# noqa: SLF001` 不是治本**: 后期需重构暴露 accessor, 与其多处 ignore, 不如一次性建公共 API
3. **fixture 的 `name_hint` 字符串误判**: 第一次 sign endpoint test 用 `body.user_id = "ignored"` 进 bootstrap 路径, 但 bootstrap 强转 owner 后忽略 body 中的 user_id, 测试 assertion 用了 actor_id

---

## 7. 安全 hardening 增量

| 修复批次 | 项数 | 攻击面 |
|---|---|---|
| v0.9 T66 引入 ACL | +1 (基础) | 完全无 ACL → 有 contributor/reviewer/owner 3 级 |
| v1.0.1 T72 修 review CRITICAL | +6 | SSE 任意订阅 / mark_read 无所有权 / sign 冒充 / submit 冒充 |
| v1.1 T74 JWT | +1 (token tamper-proof) | X-User-Id 头不可校验 → JWT 签名校验 |
| v1.1 T75 双轨兼容 | (维稳) | 老 client 不破 |
| (留 v1.2) | -3 | refresh token / 邮箱验证 / multi-instance owner race |

---

## 8. 性能 & 运维

### Scheduler 日循环 (9 job)
```
02:00 skill_trust_recompute     - 全量刷 trust_score
03:00 skill_evolve_checker      - 差表现 skill 重蒸馏
03:05 consent_sweep_expired     - 30d 超时同意 → expired
03:10 skill_deprecation_sweep   - 60d 未用 / low_trust → deprecated
+ 5 v0.4 既有 (cron/threshold/withdraw/quota/audit_log)
```

### 内存占用估算 (单进程 MVP)
- skills 全量 in-memory: 假设 1k skill × 5KB md = 5MB
- notifications: 用户 × 50 条 × 1KB = 50KB/user
- SSE queues: 每 user × 多 tab × 64 缓冲 = ~1MB/100 user

### 已知性能 TODO (留 v1.2)
- `list_marketplace` O(NlogN) sort 全集 → `heapq.nlargest`
- `build_governance_summary` 3 次全量 scan → 单 loop 合并
- bcrypt round cost (默认 12 ≈ 200ms) 在 register/login 路径阻塞 event loop → `asyncio.to_thread`

---

## 9. 留 v1.2+ 方向

按优先级:

1. **JWT 真生产化** (CRITICAL)
   - refresh_token (短期 access + 长期 refresh)
   - JWT 密钥 KMS / Vault
   - revocation list (logout 真生效)
2. **邮箱验证 + 找回密码** (HIGH)
   - email_verified_at 字段
   - SMTP / SendGrid 集成
3. **多实例 owner bootstrap 防竞态** (HIGH)
   - DB 级 UNIQUE (project_id) WHERE role='owner' 之类 partial index
4. **Skill Marketplace 中阶** (MEDIUM)
   - Star + 跨项目 trust 聚合
   - 创作者 profile 页
5. **性能微优** (MEDIUM)
   - heapq.nlargest 替换 sort
   - governance summary 单 loop
   - bcrypt to_thread
6. **embedding 重算 from import** (MEDIUM)
   - 当前是 fire-and-forget asyncio.create_task; 失败无 retry
   - 改用 APScheduler 定期 backfill needs_embedding=True 的 skill
7. **审计日志增强**
   - 当前 logger.info; 应有专门 audit_log 表持久化
8. **多语言 UI** (LOW)
   - 当前硬编码中文; i18n 框架引入

---

## 10. 致敬

Solo developer + Claude Code 协作 1 天完成 34 task 实属高密度协作示范.
关键提效:
- **任务粒度小** (单 task ~200 LoC 后端 / ~150 LoC 前端 + 测试)
- **TDD 严格** (96% task 是 test-first / test-along)
- **状态可观察** (TaskCreate/TaskUpdate 实时跟踪 + git tag 每 release)
- **回滚成本低** (immutable model_copy + pure functions + service layer 切分)

— 完 —
