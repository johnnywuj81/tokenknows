# T14 · LLM 与出域开关

## 1. 目标
配置项目内允许使用的 LLM 模型 + 出域审计开关。私有化部署的安全/合规重点。
PRD: §6.6 LLM 抽象层,§6.7 数据驻留与出域控制

## 2. 路由
- 路径: `/projects/:id/settings/llm-egress`(在 T13 设置 sub-nav 里) 或 admin `/admin/llm`
- 入口: T13 项目设置 / T15 admin 控制台
- 出口: 保存留页

## 3. 视觉参考
`docs/mockups/T14-llm-egress.html`

## 4. API

| 操作 | 端点 |
|---|---|
| 获取项目 LLM 配置 | `GET /api/v1/projects/{id}/llm-config` |
| 更新 | `PATCH /api/v1/projects/{id}/llm-config` body `{allowed_models[], egress_enabled, audit_level}` |
| 出域日志 | `GET /api/v1/egress-log?project_id=` |

## 5. 组件分解

```
src/features/admin/
├── LlmEgressPage.tsx
├── components/
│   ├── ModelAllowlist.tsx          ← 三层 toggle: 提供商 → 模型 → 版本
│   ├── EgressToggle.tsx            ← 大开关:启用/禁用出域
│   ├── AuditLevelPicker.tsx        ← off / summary / full
│   └── EgressLogTable.tsx          ← 出域日志表格(最近 100)
└── hooks/
    └── useLlmConfig.ts
```

shadcn 用: `Switch` `Card` `Badge` `Table` `Select` `Dialog`(关闭出域确认)

## 6. 状态管理

- 配置 form: react-hook-form,有 unsaved indicator
- 日志: TanStack Query 分页

## 7. 必备状态

- [ ] Loading: 配置加载骨架
- [ ] Empty: 出域日志空 → "近期无出域记录"
- [ ] Error: 重试
- [ ] Success: 保存后 toast

## 8. 验收

- [ ] 三层 toggle: 提供商(OpenAI/Anthropic/本地)→ 模型(gpt-4o/claude-3.5)→ 版本/特性
- [ ] 关闭出域 = 只能用本地模型;关闭时弹 dialog 警示"将无法使用云端 LLM"
- [ ] 审计级别: off / summary(只记调用次数)/ full(记完整 prompt + response)
- [ ] 出域日志表格列: 时间 / 模型 / 用户 / token 用量 / 响应耗时 / hash
- [ ] full 审计下显示"查看详情"展开 prompt(脱敏后)
- [ ] 表头有筛选: 时间范围 / 模型 / 用户
- [ ] 整页只对 admin / project owner 可见

## 9. 已知陷阱

- 出域开关变更要立即生效(后端 fastapi 中间件读 cache 即可),不要等用户重新登录
- 模型 allowlist 改了之后,T08 重生成对话框里要刷新模型列表
- 审计日志可能巨大,默认只显示 7 天,有"加载更早"
- 此页操作全部进 audit log(改配置 = 高风险操作)

## 10. Claude Code 指令
三层 toggle 用嵌套 `Switch`,父开关关上时子项 disabled。
