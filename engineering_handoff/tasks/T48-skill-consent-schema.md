# T48 · Skill 状态机扩展 + Contributor 同意 Tracking 字段

> v0.5.1 第一块（Q5 决策落地的基础设施）。
> Proposal: [v0.5 §3.1 状态机 / §3.3 数据模型](../../Proposal_OnDemand_and_ContributorConsent_v0.5.md)

## 1. 目标
Skill 自动蒸馏（v0.4.2 T42）出来后不再直接进 `draft`，而是先停在 `pending_contributor_consent`，等所有 contributor 同意才转 draft。Q5 决策"必须个人确认"的合规闸门。

## 2. 范围
- **In**: `Skill.status` Literal 加 3 个新值、4 个新字段、DB migration、`Skill.contributors` 派生 `consent_required_from`
- **Out**: 通知发送（T49）、sign/reject endpoint（T50）、UI（T51）

## 3. 状态机扩展

```
distill_skill (auto / @机器人 触发, 且 contributors 非空)
    ↓
status='pending_contributor_consent'  ← v0.5 新增
    ↓ (所有 contributor 都 sign)
status='draft'  ← 与手动蒸馏一致
    ↓ ...

任一 contributor reject → status='rejected_by_contributor'  ← v0.5 新增
30 天无人响应       → status='expired_no_consent'           ← v0.5 新增
```

合法转换矩阵：

| from \ to | pending | draft | rejected_by_c | expired_no_c | active | locked | deprecated |
|---|---|---|---|---|---|---|---|
| pending | — | ✅ 全员签 | ✅ 任一拒 | ✅ 超 30d | — | — | — |
| draft | — | — | — | — | ✅ | ✅ | ✅ |
| rejected_by_c | — | — | — | — | — | — | ✅ 仅归档 |
| expired_no_c | — | — | — | — | — | — | ✅ 仅归档 |

## 4. Pydantic 扩展

```python
# app/schemas/skill.py

SkillStatus = Literal[
    "draft", "active", "deprecated", "locked",
    # v0.5 新增:
    "pending_contributor_consent",
    "rejected_by_contributor",
    "expired_no_consent",
]

class Skill(BaseModel):
    # ... 现有字段 ...
    status: SkillStatus

    # v0.5 新增 4 字段
    consent_required_from: list[str] = Field(default_factory=list)
    """需同意的 contributor user_id 列表 (从 Skill.contributors 派生; init 时一次性设)"""

    consent_signed_by: list[ConsentRecord] = Field(default_factory=list)
    """已签字: [{user_id, signed_at, channel: 'im_dm'|'web', note?}]"""

    consent_rejected_by: ConsentRecord | None = None
    """首位拒绝者 (rejected 后冻结); 后续即使其他人签也无效"""

    consent_expires_at: datetime | None = None
    """OD-6: initialize_pending 时 +30 天; 超时由 daily sweep 转 expired"""


class ConsentRecord(BaseModel):
    user_id: str
    signed_at: datetime
    channel: Literal["im_dm", "web"]
    note: str | None = None
```

## 5. DB Migration

`skills` 表 json 字段已存完整 Skill dump，**Pydantic 加字段后无需改 schema.sql**。但需要给现有 active/draft skill 反序列化兼容：

```python
# app/schemas/skill.py 加 model_validator
@model_validator(mode="before")
def _backfill_consent_fields(cls, values):
    """v0.4 之前的 skill 无这些字段; load 时填 default."""
    values.setdefault("consent_required_from", [])
    values.setdefault("consent_signed_by", [])
    values.setdefault("consent_rejected_by", None)
    values.setdefault("consent_expires_at", None)
    return values
```

无 DB DDL 改动，老数据 round-trip 安全。

## 6. 组件分解

```
backend/app/schemas/skill.py          ← 加 3 status + 4 字段 + ConsentRecord + validator
backend/app/services/skill/
├── consent.py                        ← T48 新模块
│   ├── initialize_pending(skill) → 写 consent_required_from + expires_at
│   ├── can_transition(from, to) → bool
│   └── check_all_signed(skill) → bool
backend/tests/test_skill_consent_schema.py
```

## 7. 必备状态（DoD）
- [ ] SkillStatus 7 种状态全部 Literal-typed; non-literal 字符串 Pydantic 校验失败
- [ ] 老数据 (v0.4 之前) load 时自动 backfill 4 个新字段 (default value)
- [ ] `initialize_pending` 写 `consent_required_from` = `[c.user_id for c in skill.contributors]` + `consent_expires_at = now + 30d`
- [ ] `check_all_signed` 边界：required=[] 视为 True (无 contributor 即视为已同意); required=[a, b] 且 signed=[a] → False
- [ ] `can_transition` 矩阵全覆盖（见 §3）

## 8. 验收
- [ ] Pydantic round-trip 测试覆盖 7 种 status + 4 个新字段
- [ ] 旧 skill JSON 反序列化不报错 + 4 新字段为 default
- [ ] 状态机非法转换抛 `InvalidTransition`
- [ ] consent_required_from 不可手动改（只在 initialize_pending 内写）

## 9. 已知陷阱
- 老的 SKILL.md 已经 draft/active 状态，**不要**自动加 pending；只对 v0.5 之后新蒸馏的加
- `Skill.contributors` 可能为空（手动蒸馏没传 chapter→user 映射），此时 `initialize_pending` 跳过 → 直接 draft
- `consent_expires_at` 用 UTC datetime；与 APScheduler sweep_expired_consents 时区对齐
- `consent_rejected_by` 是单值（首位拒绝者冻结），不要存数组；后续即使第 2 个 reject 不再写
- migration 不需要 ALTER TABLE，但 model_validator 必须用 `mode="before"`（在 Pydantic 字段填充前注入 default）

## 10. Claude Code 指令
顺序：先扩 Pydantic schema + 4 字段 + validator → 写 `consent.py` 的 `initialize_pending` / `check_all_signed` / `can_transition` 纯函数 → 测试。**不要**在 T48 内集成到 dispatcher (T49)；不要写通知发送 (T49)；不要写 endpoint (T50)。
