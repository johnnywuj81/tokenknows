# T02 · 项目创建 + 数据源向导

## 1. 目标
新用户登录后第一件事:建项目 + 接入至少 1 个数据源(Claude Code / Cursor / VS Code / GitHub)。
PRD: §4.1 旅程 A,§5.1 模块 A · 数据源接入

## 2. 路由
- 入口: `/projects/new`(从工作台空态/侧边栏 "+ 新建项目" 进)
- 出口: 完成后跳 `/projects/:id`

## 3. 视觉参考
`docs/mockups/T02-project-setup.html` · 4 步向导(基本信息 / 数据源选择 / 接入指引 / 完成)

## 4. API

| 操作 | 端点 |
|---|---|
| 创建项目 | `POST /api/v1/projects` body `{name, description, visibility}` |
| 列数据源 | `GET /api/v1/projects/{id}/datasources` |
| 接 GitHub | `POST /api/v1/projects/{id}/datasources/github` body `{repo_url, access_token}` |
| 接本地文件 | `POST /api/v1/projects/{id}/datasources/local-file`(返回上传 URL) |
| 拿插件 token | 创建项目时后端会自动生成,从 project 响应里取 |

## 5. 组件分解

```
src/features/projects/
├── NewProjectPage.tsx           ← 多步向导外壳
├── components/
│   ├── WizardStepper.tsx        ← 顶部进度条
│   ├── StepBasicInfo.tsx        ← Step 1: 名称、简介、可见性
│   ├── StepDataSource.tsx       ← Step 2: 4 个数据源卡片
│   ├── StepIntegration.tsx      ← Step 3: 当前选中数据源的接入指引
│   ├── StepDone.tsx             ← Step 4: 完成 + 下一步引导
│   └── integrations/
│       ├── ClaudeCodeCard.tsx   ← 显示 plugin 安装命令 + 连接 token
│       ├── CursorCard.tsx
│       ├── VsCodeCard.tsx
│       └── GitHubCard.tsx       ← OAuth 跳转 / 输入 repo URL + PAT
└── hooks/
    └── useCreateProject.ts
```

shadcn 用: `Card` `Input` `Textarea` `Button` `RadioGroup` `Tabs` `Progress` `Badge`

## 6. 状态管理

- 向导本地 state: `useReducer`(4 步状态机)
- 创建后 invalidate `['projects']` 让工作台刷新

## 7. 必备状态

- [ ] Loading: 创建项目时,主按钮 spinner
- [ ] Empty: 不适用(向导本身就是创建)
- [ ] Error: 行级 + toast。GitHub repo URL 校验失败立即提示
- [ ] Success: Step 4 显示绿色对勾 + "进入工作台"主按钮

## 8. 验收

- [ ] 4 步可以前进/后退,后退保留已填数据
- [ ] Step 2 选数据源时,可以多选(GitHub + Claude Code 同时接)
- [ ] Step 3 每个数据源的接入指引内容不同(看 mockup)
- [ ] Claude Code / Cursor 那俩卡显示连接 token,有"复制"按钮 + 复制成功 toast
- [ ] GitHub 卡支持 PAT 接入(MVP 不做 OAuth)
- [ ] Step 4 显示项目名 + 接入的数据源 + "去工作台"按钮
- [ ] 整个向导可以中途关闭(返回工作台,丢弃数据,有确认 dialog)

## 9. 已知陷阱

- 连接 token 是敏感信息,UI 上默认遮蔽,需要点"显示"才看见
- GitHub PAT 校验需要后端验证,不要在前端只做正则
- 项目名不能重名(同一 user),后端会返回 409,前端要友好提示

## 10. Claude Code 指令
先把 useReducer 状态机写好,再写 4 个 step 组件(都是纯展示),最后接 API。
