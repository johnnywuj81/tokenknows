# T15 · 实例管理员控制台

## 1. 目标
私有化部署的实例总览:用户 / 项目 / 配额 / 审计日志。深色 header,管理员专用。
PRD: §6.5 部署与交付,§6.3 可观测性

## 2. 路由
- 路径: `/admin`(子路径:`/admin/users` `/admin/quotas` `/admin/audit`)
- 入口: 头像下拉"实例管理"(仅 superadmin 可见)
- 出口: 切回普通工作区

## 3. 视觉参考
`docs/mockups/T15-admin.html` · 深色 header(`bg-inverse-bg`) + 四个数字卡 + 表格

## 4. API

| 操作 | 端点 |
|---|---|
| 实例统计 | `GET /api/v1/admin/stats` |
| 用户列表 | `GET /api/v1/admin/users` |
| 项目列表 | `GET /api/v1/admin/projects` |
| 配额 | `GET/PATCH /api/v1/admin/quotas` |
| 审计日志 | `GET /api/v1/audit-log` |

## 5. 组件分解

```
src/features/admin/
├── AdminLayout.tsx                 ← 深色 header + sub-nav
├── AdminStatsPage.tsx              ← /admin 首页:4 个数字卡 + 图表
├── AdminUsersPage.tsx              ← /admin/users
├── AdminQuotasPage.tsx             ← /admin/quotas
├── AdminAuditPage.tsx              ← /admin/audit
└── components/
    ├── StatCard.tsx                ← 大数字卡(用 font-content 字体)
    ├── UserRow.tsx
    ├── QuotaBar.tsx                ← Progress + 已用/总数
    └── AuditFilters.tsx
```

shadcn 用: `Card` `Table` `Badge` `Button` `Progress` `Input` `Select` `DropdownMenu`
图表(可选):`recharts` 简单折线

## 6. 状态管理
全部只读 / 表单更新,TanStack Query。

## 7. 必备状态

- [ ] Loading: stats 卡骨架 + 表格 skeleton
- [ ] Empty: 用户/项目 0 个 → 友好提示
- [ ] Error: 行级
- [ ] Success: 表格

## 8. 验收

- [ ] 深色 header (`bg-inverse-bg text-inverse-text`),与其他屏视觉区分明显
- [ ] 实例统计页 4 个数字卡: 用户数 / 项目数 / 本月生成文档数 / 本月 LLM token 用量
- [ ] 用户表格列: 头像 / 邮箱 / 角色 / 项目数 / 最后活跃 / 操作(禁用/重置密码)
- [ ] 配额页: 每个项目的 LLM token 配额 + 存储配额 + 用量进度条
- [ ] 配额 80% 显示橙色,100% 红色
- [ ] 审计日志: 操作时间 / 操作人 / 资源 / 动作 / IP / 详情
- [ ] 审计筛选: 用户 / 动作类型 / 时间范围 / 资源
- [ ] 整页非 superadmin 进入 → 403 + 跳回 `/`
- [ ] 顶部"导出审计日志"按钮:CSV 下载

## 9. 已知陷阱

- 权限检查在路由 guard + 后端双重校验,前端不要只靠 UI 隐藏
- 审计日志条数极大,默认显示 100,有 cursor 分页
- 修改配额是高风险操作,弹 dialog 确认 + 进自己的 audit log
- 深色 header 内的按钮要用 `bg-inverse-accent` 不是普通 `bg-accent-primary`

## 10. Claude Code 指令
admin 路由全部走单独的 `AdminLayout`,header 深色不复用普通 layout。
