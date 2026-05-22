# T30 · TriggerDispatcher（5 分钟撤回窗口 + 调 generation pipeline）

## 1. 目标
T29 命中后写 scheduled execution，本任务负责"撤回窗口结束 → 实际调 LLM → 生成 asset"。
Proposal: §2.1 频率约束 / §7.5 AT-E / 决策 AT-4 / §9.4 与 LLM Gateway 协作

## 2. 范围
- **In**: TriggerDispatcher 主类、与 generation_service 对接、写入 asset.trigger_meta、错误处理
- **Out**: withdraw_window_resolver 后台 job（T31 调度，本任务只实现 dispatcher 单次执行函数）

## 3. 调度契约

```
TriggerDispatcher.fire(execution_id):
1. 加载 trigger_execution + trigger_rule
2. 双重校验:
   a. execution.status 必须是 'scheduled'
   b. execution.fire_at <= now (撤回窗口已过)
3. 调 generation_service.generate_asset(
     project_id=rule.project_id,
     asset_type=rule.asset_type,
     trigger_meta={
       trigger_mode, rule_id, rule_name, signal, confidence, fired_at,
     },
   )
4. asset 创建成功:
   - execution.asset_id = asset.id
   - execution.status = 'fired'
   - execution.fired_at = now
   - SSE 推 auto_trigger.fired
5. 失败:
   - execution.status = 'failed'
   - execution.error_message = str(e)
   - 通知 Owner（v0.4.0 仅 audit log，邮件留 v0.4.4）
```

## 4. 组件分解

```
backend/src/auto_trigger/
├── dispatcher/
│   ├── trigger_dispatcher.py   ← 主类 fire(execution_id)
│   ├── meta_builder.py         ← 组装 asset.trigger_meta JSON
│   └── error_handler.py        ← 分类错误（LLM 超时 / quota / 参数错）
└── tests/
    ├── test_dispatcher.py
    └── test_meta_builder.py
```

## 5. 与 generation_service 的协作

复用 MVP 现有的 `generation_service.generate_asset()`，新增可选参数 `trigger_meta: dict | None = None`：
- 内部把 `trigger_meta` 写到 `asset.trigger_meta`（T26 patch 的字段）
- 同时把 `trigger_execution_id` 关联到 asset（反查用）
- 其他流程（LLM 调用 / SSE / 出域审计）与手动生成完全相同

## 6. 必备状态（DoD）
- [ ] 调用 dispatcher.fire() 后 trigger_execution.status 进入 fired 或 failed
- [ ] asset 创建后 asset.trigger_meta 完整：rule_id / rule_name / signal / confidence / fired_at
- [ ] LLM 调用失败 → execution.error_message 详细（含 LLM provider / model / token 用量）
- [ ] 重入安全：同一 execution_id 被 fire 两次 → 第二次返回 already_fired，不重复调 LLM

## 7. 验收
- [ ] 单测：mock generation_service 后跑 dispatcher → 状态正确
- [ ] 集成测试：真实跑一条"周一周报"规则的 dispatcher，asset 在 DB 里能查到，trigger_meta 完整
- [ ] LLM 超时（mock provider 30s 不响应）→ execution.status=failed 且 audit_log 记录
- [ ] 撤回窗口未过（fire_at > now）调用 fire() → 抛 PrematureFireError

## 8. 已知陷阱
- generation_service.generate_asset() 是 long-running（含 LLM 调用，可能 30s+），dispatcher 必须 async；不要在调度器线程内同步等
- LLM 调用前不预扣 quota（v0.4.0 不实现 quota），但要记 audit log
- trigger_meta JSON 字段不能套 datetime（要序列化为 ISO 字符串），meta_builder 负责
- 重入：用 execution.status 作为原子检查（status='scheduled' → 'firing' 用 SELECT FOR UPDATE）
- 错误分类：LLM provider 错（可重试）vs 业务参数错（不可重试） → error_handler 区分

## 9. Claude Code 指令
顺序：meta_builder（纯函数易测）→ error_handler → trigger_dispatcher 主类 → 接 generation_service。重入测试要用 asyncio.gather 并发触发 100 次同 execution_id，断言只 fire 1 次。
