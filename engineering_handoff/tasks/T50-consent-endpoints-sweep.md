# T50 · Sign/Reject Endpoints + 每天 sweep_expired_consents

> v0.5.1 第三块。完成 Skill 同意流程的"读写闭环"。
> Proposal: [v0.5 §3.4 用户旅程 / OD-6 / OD-10](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
让 contributor 通过 REST（前端 T51 / IM 跳链接 / 邮件链接）真正完成同意 / 拒绝，并在系统层面：
- 全员同意 → Skill 转 `draft`（进 Reviewer 审批流）
- 任一拒绝 → Skill 转 `rejected_by_contributor`
- 30 天无响应 → 每天 03:00 sweep 自动转 `expired_no_consent`

## 2. 范围
- **In**: 2 个 REST endpoint、APScheduler sweep_expired_consents job、SSE 事件 `auto_trigger.consent_signed/rejected/expired`
- **Out**: 前端 UI（T51）、通知发送（T49）

## 3. REST API

### 3.1 POST `/api/v1/skills/:skill_id/consent/sign`

```python
# body
{
  "channel": "web" | "im_dm",
  "note": "可选 ≤ 200 字"  # 说明同意理由
}

# 401 if not authenticated
# 403 if user_id not in skill.consent_required_from
# 409 if skill.status != "pending_contributor_consent"
# 200 OK
{
  "skill_id": "skill-xxx",
  "current_status": "pending_contributor_consent" | "draft",  # 全签后跳 draft
  "signed_count": 2,
  "required_count": 3,
  "all_signed": false  # 还差 1
}
```

### 3.2 POST `/api/v1/skills/:skill_id/consent/reject`

```python
# body
{
  "channel": "web" | "im_dm",
  "reason": "≤ 500 字"  # 必填; 用于审计 + 后续 SignalGate 调权
}

# 同样 401/403/409
# 200 OK
{
  "skill_id": "skill-xxx",
  "current_status": "rejected_by_contributor",
  "rejected_by": "ou_alice"
}
```

## 4. sweep_expired_consents job

APScheduler 新增（注册在 `scheduler.py`）：

```python
# 每天 03:00 (Asia/Shanghai)
scheduler.add_job(
    sweep_expired_consents_job,
    CronTrigger(hour=3, minute=0),
    id="consent_sweep_expired",
    replace_existing=True,
)
```

实现：

```python
# app/services/skill/consent.py
def sweep_expired_consents() -> dict[str, int]:
    """扫所有 status='pending_contributor_consent' 且 consent_expires_at < now 的 Skill,
    转 expired_no_consent + 发 SSE consent_expired."""
    now = datetime.now(timezone.utc)
    pending = skill_service.list_pending_consent_skills()
    n = 0
    for skill in pending:
        if skill.consent_expires_at and skill.consent_expires_at < now:
            skill_service.update_skill(skill.id, status="expired_no_consent")
            sse.publish("auto_trigger.consent_expired", {...})
            n += 1
    logger.info("consent_sweep_expired", count=n)
    return {"expired": n}
```

## 5. SSE 事件

| 事件 | 触发 | payload |
|---|---|---|
| `auto_trigger.consent_signed` | sign endpoint 成功 | `{skill_id, signed_by, signed_count, required_count, all_signed}` |
| `auto_trigger.consent_rejected` | reject endpoint 成功 | `{skill_id, rejected_by, reason}` |
| `auto_trigger.consent_expired` | sweep job 转 expired | `{skill_id, expired_at}` |

订阅范围：发给 `consent_required_from` 列表里的所有 user（让其他 contributor 知道同伴已经签/拒）。

## 6. 组件分解

```
backend/app/gateway/http_api/
├── skills.py                  ← 加 2 个 endpoint
backend/app/services/skill/
├── consent.py                 ← T48 已有部分 + sweep_expired
backend/app/services/auto_trigger/
├── scheduler.py               ← 注册 consent_sweep_expired job
backend/app/services/sse_service.py    ← 加 publish 3 个新 event

backend/tests/test_skill_consent_endpoints.py
backend/tests/test_consent_sweep.py
```

## 7. 必备状态（DoD）
- [ ] sign / reject 双 endpoint 鉴权 + 状态校验 + 幂等（同一用户 2 次 sign 不报错，但只计一次）
- [ ] 全员签 → 自动 status='draft' + 触发 SSE
- [ ] 任一拒绝 → 立即 status='rejected_by_contributor' + 冻结后续签字
- [ ] sweep_expired_consents 每天 03:00 自动跑（验证 APScheduler 注册）
- [ ] 30 天未响应自动转 expired

## 8. 验收
- [ ] 单测：4 个状态机分支 (pending → draft / rejected / expired / 仍 pending)
- [ ] 单测：sign endpoint 鉴权 (用户不在 required_from → 403)
- [ ] 单测：sign endpoint 状态 (skill 已 active → 409)
- [ ] 单测：sweep 用 freezegun 模拟 31 天后
- [ ] 集成：3 contributor 场景 (2 签 1 待 / 全签 / 1 拒)

## 9. 已知陷阱
- 同一 contributor 重复 sign：第二次返 200 但不重复写入 consent_signed_by 列表（去重 by user_id）
- contributor 同时 sign 和别人 reject 并发：用 store 层 SELECT FOR UPDATE 防止状态机错乱（v0.5.1 单实例可用乐观锁）
- "全员签"检查必须在 sign endpoint **内**做并立即转 draft，不要异步（否则 SSE 推送时机不对）
- reject 后即使 expired_at 还没到，sweep 也不应再扫它（status != pending 时跳过）
- sweep 失败不应阻塞下次：try/except per skill
- SSE 推送的 user_id 路由要严格（只发给 contributor，不广播给 owner / reviewer）

## 10. Claude Code 指令
顺序：写 endpoint 主体（含权限校验 + 状态机调用）→ 接 T48 consent.py 的 `sign_consent`/`reject_consent` 函数 → sweep job 单写（独立可测）→ 注册 APScheduler → SSE 推送整合。先用 freezegun 测 sweep，再做端到端集成测。
