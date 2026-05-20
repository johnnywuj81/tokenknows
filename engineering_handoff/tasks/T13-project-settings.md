# T13 · 项目设置

## 1. 目标
项目级配置:基本信息、成员、数据源、脱敏规则、删除。
PRD: §5.1 / §5.6 / §6.7

## 2. 路由
- 路径: `/projects/:id/settings`(默认 tab=info)/ `/projects/:id/settings/members` 等
- 入口: 工作台右上角项目菜单"项目设置"
- 出口: 保存后留页或返回工作台

## 3. 视觉参考
`docs/mockups/T13-project-settings.html` · 左侧 sub-nav + 右侧表单/表格

## 4. API

| 操作 | 端点 |
|---|---|
| 基本信息更新 | `PATCH /api/v1/projects/{id}` |
| 删除项目 | `DELETE /api/v1/projects/{id}` |
| 成员 CRUD | `GET/POST/PATCH/DELETE /api/v1/projects/{id}/members` |
| 数据源列表 | `GET /api/v1/projects/{id}/datasources` |
| 健康检查 | `GET /api/v1/projects/{id}/datasources/{ds_id}/health` |
| 删除数据源 | `DELETE /api/v1/projects/{id}/datasources/{ds_id}` |

## 5. 组件分解

```
src/features/settings/
├── ProjectSettingsPage.tsx
├── tabs/
│   ├── InfoTab.tsx                 ← 名称 / 简介 / 可见性 / 删除区
│   ├── MembersTab.tsx              ← 成员表格 + 邀请 dialog
│   ├── DataSourcesTab.tsx          ← 数据源列表 + 健康状态 + 新增按钮(复用 T02 卡片)
│   └── RedactionRulesTab.tsx       ← 自定义脱敏规则(MVP 简化:正则列表)
├── components/
│   ├── SubNav.tsx                  ← 左侧 nav
│   ├── DangerZone.tsx              ← 红色 border 的危险操作区
│   └── InviteMemberDialog.tsx
└── hooks/
    ├── useProjectUpdate.ts
    └── useMembers.ts
```

shadcn 用: `Tabs` `Card` `Table` `Input` `Button` `Dialog` `Badge` `Switch` `Select` `Textarea`

## 6. 状态管理

- 当前 tab: URL `/settings/:tab`
- 表单: react-hook-form,字段保存按钮在每个区块底部

## 7. 必备状态

- [ ] Loading: 每个 tab 内部骨架
- [ ] Empty: 成员只有自己 / 数据源 0 个 → 友好提示
- [ ] Error: 行级
- [ ] Success: 保存后绿对勾 + "已保存"

## 8. 验收

- [ ] 三/四个 tab 切换走 URL,刷新保留
- [ ] InfoTab: 项目名、简介、可见性(Radio)/ DangerZone 删除带 dialog 确认输入项目名
- [ ] MembersTab: 表格列(头像 / 邮箱 / 角色 / 加入时间 / 操作);邀请 dialog 输入邮箱 + 选角色
- [ ] DataSourcesTab: 各数据源卡片显示健康状态(绿/黄/红)+ 最后同步时间 + 重连/删除
- [ ] RedactionRulesTab: 列表 + 新增正则规则 + 测试输入框(实时高亮匹配)
- [ ] 角色 = admin 才能编辑;viewer / member 看不见 DangerZone
- [ ] 数据源删除二次确认,提示"已生成文档不会受影响"

## 9. 已知陷阱

- 邀请成员发送邮件是后端工作,前端只 POST 等响应
- 不能把自己从项目里删,UI 上隐藏自己那行的"删除"
- 数据源健康检查可能很慢,显示 spinner + 上次结果
- 脱敏正则测试要 debounce 不要每次按键都跑

## 10. Claude Code 指令
四个 tab 内容差异大,各自独立 component,共享 SubNav 即可。
