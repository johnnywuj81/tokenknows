# TokenKnows MVP — 工程施工手册

> **历史档说明** · 本目录是 MVP 阶段的工程交接记录(sprint 计划 / 架构 / 任务包 / demo),
> 按当时原貌保留 —— 文内出现的绝对路径、端口、机器名反映的是初始开发机环境,
> 不代表当前安装方式;新人上手请从 [仓库根 README](../README.md) 与
> [CONTRIBUTING](../CONTRIBUTING.md) 开始。

**给 1 个人 + Claude Code/Cursor 用的版本**。跳过 Figma 环节,基于现有 HTML mockup 直接开工。

---

## 🎯 这份手册解决什么

你已经有的:PRD、TDD、DesignHandoff、15 个 HTML mockup。
你缺的:一份能让 AI 代理顺着做下来、不漏需求、不跑偏的"施工动线"。

这里给你的不是新文档,是**把现有文档串成 AI 能直接消费的任务流**:

```
1. 跑 00-bootstrap.md 里的命令 → 拿到一个开箱即用的 React 仓库
2. 把 CLAUDE.md 放到仓库根 → Claude Code 自动获得项目全局上下文
3. 按 sprint 计划,逐屏 cat tasks/T0X-*.md 喂给 Claude Code → 每屏 30–90 分钟搞定
4. 跑验收清单 → 这屏完成,进入下一屏
```

---

## 📁 包内文件

```
engineering_handoff/
├── README.md                ← 你正在看
├── 00-bootstrap.md          ← 前端项目初始化命令(一次性)
├── bootstrap-step1-3.sh     ← 第 1-3 节的自动化脚本
├── dev-env-setup.md         ← nvm + uv + Docker Compose 隔离指南
├── CLAUDE.md                ← 复制到仓库根,作为 Claude Code 全局记忆
├── tailwind.config.ts       ← 直接覆盖 vite 默认配置
├── tokens.css               ← CSS 变量(可选)
└── tasks/
    ├── _template.md         ← 任务包模板
    ├── T01-auth.md          ← Sprint 1 (Week 1)
    ├── T02-project-setup.md
    ├── T03-workbench.md
    ├── T04-event-detail.md  ← Sprint 3 (Week 3)
    ├── T05-document-list.md ← Sprint 2 (Week 2)
    ├── T06-document-page.md
    ├── T07-evidence-drawer.md
    ├── T08-regenerate-dialog.md
    ├── T09-review.md        ← Sprint 3 (Week 3)
    ├── T10-redaction.md
    ├── T11-publish.md
    ├── T12-publish-receipt.md
    ├── T13-project-settings.md  ← v0.2 (本期不做)
    ├── T14-llm-egress.md        ← v0.2
    └── T15-admin.md             ← v0.2
```

---

## 🗓 4 周 Sprint 计划 · 闭环优先(全职 6-8h/天)

**目标**: 4 周拿到一个能跳意向客户的完整产品 — 从注册到发布的全链路 (T01-T12) 跑通。
T13/T14/T15(项目设置/LLM 出域/管理员)任务包已写好,但**不进本期 sprint**,留作 v0.2 扩展。

按依赖顺序排,不是按优先级 — 因为 solo 最大风险是"卡在中间发现前面缺数据"。

### 第 1 周 · 地基 + 进得来 (Day 1-5)

目标: 用户能登录、建项目、看到工作台。

| Day | 任务 | 时长估计 | 验收 |
|---|---|---|---|
| 1 | 跑 `00-bootstrap.md` + 路由 + AppLayout 骨架 + 通用 EmptyState/ErrorState/Skeleton 组件 | 6h | `npm run dev` 进得去,空页 + 通用状态组件齐全 |
| 2 | `T01-auth.md` 注册/登录/邮箱验证/找回密码(4 个子页) | 7h | 4 屏全部能切换,mock auth 走通,localStorage 存 token |
| 3 | `T02-project-setup.md` 上半:Step 1+2(基本信息 + 数据源选择) | 6h | 前 2 步向导走通,数据源 4 卡可选 |
| 4 | `T02-project-setup.md` 下半:Step 3+4(接入指引 + 完成) | 6h | Claude Code / Cursor / VS Code / GitHub 4 个接入卡完整,token 复制 toast |
| 5 | `T03-workbench.md` 工作台首页 + polling 实时事件流 | 8h | 三栏布局对齐 mockup,polling 30s 刷新,空态/错误态齐全 |

**里程碑 1 (周五)**: 录屏 demo — 注册账号 → 建项目 → 看工作台。**全 MSW mock,无需后端**。

### 第 2 周 · 文档生成核心环路 (Day 6-10)

目标: 文档生成结果页能看、能改、能查证据。**产品的核心卖点。**

| Day | 任务 | 时长估计 | 验收 |
|---|---|---|---|
| 6 | `T05-document-list.md` 文档列表 + 触发生成按钮 | 6h | 卡片网格、筛选、生成中 progress |
| 7 | `T06-document-page.md` 阶段 1:三栏布局 + 静态章节渲染 (markdown-it,先不上 TipTap) | 8h | 大纲锚点联动、章节卡静态对齐 mockup |
| 8 | `T06-document-page.md` 阶段 2:TipTap + 自动保存 | 8h | 编辑章节、debounce 2s 自动 PATCH,顶部"已保存"状态机 |
| 9 | `T07-evidence-drawer.md` 证据链抽屉 + 内联证据角标联动 | 7h | 章节内 `[3]` 可点 → 抽屉打开定位证据 3,切换证据不重开 drawer |
| 10 | `T08-regenerate-dialog.md` 章节重生成对话框 + 章节"生成中"状态显示 | 6h | 模型选择 + instruction 编辑,提交后章节进入 loading 态 |

**里程碑 2 (周五)**: 录屏 demo — 打开 mock 文档 → 改章节 → 看证据 → 重生成。这是给客户看的"魔法时刻"。

### 第 3 周 · 协作 + 合规 + 发布 (Day 11-15)

目标: 一篇文档走完"草稿 → 审批 → 脱敏 → 发布"完整流程。

| Day | 任务 | 时长估计 | 验收 |
|---|---|---|---|
| 11 | `T04-event-detail.md` 事件详情抽屉(工作台 + 文档页都能弹) | 5h | 时间轴 + 元数据 + 跳转生成文档 |
| 12 | `T09-review.md` Reviewer 审批视图(只读文档 + 批注 + 通过/退回) | 8h | 章节级通过/退回、批注 thread、全部通过后→ 发布按钮 |
| 13 | `T10-redaction.md` 脱敏确认面板(异步 scan + polling) | 7h | PII 命中分组、单/批量脱敏、豁免理由 |
| 14 | `T11-publish.md` 发布对话框(站内 + 公开链接 + 导出) | 6h | 三种渠道多选、确认清单、export 文件下载 |
| 15 | `T12-publish-receipt.md` 发布回执 + 版本 diff | 7h | 大对勾 + 渠道链接 + diff 三栏(增/改/删) |

**里程碑 3 (周五)**: 录屏 demo — 一篇文档从 T06 编辑 → T09 审批 → T10 脱敏 → T11 发布 → T12 回执,全链路 30 分钟内跑通。**这就是 v0.1 MVP**。

### 第 4 周 · 接真后端 + e2e + 打磨 (Day 16-20)

| Day | 任务 | 时长估计 | 验收 |
|---|---|---|---|
| 16 | 后端联调:替换 MSW handlers 为真实 API,修类型不匹配 | 8h | 12 屏接通真 FastAPI,无 mock 残留 |
| 17 | 真实 SSE 替换工作台 polling + 后端事件实时推送 | 6h | T03 工作台收到 push 不刷新页面 |
| 18 | e2e 主链路测试(Playwright):注册 → 建项目 → 生成文档 → 发布 全跑一遍 | 6h | 1 个 e2e 脚本通过 |
| 19 | UI 打磨:对照 mockup 截图逐屏 review,修视觉偏差;a11y 检查(Tab 顺序 + 焦点) | 7h | 12 屏视觉与 mockup ≥ 95% 对齐 |
| 20 | Buffer / 修 bug / 准备 demo / 录 5 分钟 演示视频 | 8h | 演示视频成品,可以直接发给客户 |

**里程碑 4 (周末)**: v0.1 MVP 上线候选 — 自己内部装一台演示环境,3 分钟内能从零开始走完一次全链路。

---

## ⏱ 节奏自检

如果发现某天延后:

| 哪里慢了 | 怎么处理 |
|---|---|
| Day 7-8(T06 文档页)超时 | 牺牲第 4 周 Day 19 的 UI 打磨,T06 是核心不能减 |
| Day 16(联调)超过 1 天 | 把 e2e (Day 18) 从 Playwright 简化为 vitest + happy-dom 跑 hook 单测 |
| 整体慢半周以上 | 砍 T04(事件详情)和 T10(脱敏)进 v0.2;v0.1 没有这俩也能给客户看 |
| 砍后还慢 | 砍 T09 审批,文档"提交"按钮直接进 T11 发布 |

**绝对不要砍**: T01 / T02 / T03 / T05 / T06 / T07 / T11 / T12。这 8 屏砍掉任何一个都跑不通主链路。

---

## 🤖 怎么和 Claude Code 配合干活

每屏一个工作循环:

```bash
# 1. 进项目根目录
cd ~/code/tokenknows-web

# 2. 启动 Claude Code
claude

# 3. 喂任务包
> 请按 ../engineering_handoff/tasks/T03-workbench.md 实现工作台首页。
> 完成后跑验收清单,有疑问先问。

# 4. Claude Code 会:
#    - 读 mockup HTML (../mockups/T03-workbench.html)
#    - 读 PRD §8 相关章节
#    - 创建/修改对应组件、路由、API hook
#    - 跑 lint / typecheck
#    - 报告完成状态

# 5. 你做验收:对照 mockup 截图,逐项过 checklist
```

### 喂任务包前要做的

- ✅ 把 mockup HTML 文件夹放到仓库的 `docs/mockups/`(或软链)
- ✅ 把 `CLAUDE.md` 放到仓库根
- ✅ 把 `engineering_handoff/` 也放在仓库下,任务包用相对路径
- ✅ 仓库初始化好 git,每屏完成后 commit 一次

### 任务包都包含什么

每个 `tasks/T0X-*.md` 长这样(详见 `_template.md`):

```
1. 目标 / 屏幕作用       ← AI 知道这屏在哪个用户旅程
2. 路由 + 入口            ← React Router 路径、上游链接
3. Mockup 引用            ← HTML 文件路径,AI 用来做像素参考
4. 数据源 / API           ← 用哪些后端接口、TanStack Query key
5. 组件分解               ← shadcn/ui 用哪些、自己写哪些
6. 状态管理               ← Zustand store 字段 / Query cache
7. 必备状态               ← loading / empty / error / success
8. 验收清单 (Definition of Done)
9. 已知陷阱 / 注意事项
```

---

## 🔧 推荐工作流细节

### Mock 优先,后端最后接

第 1-3 周全部用 [MSW](https://mswjs.io/) 模拟后端。好处:
- 前端独立推进,不被 FastAPI 进度卡住
- mock handler 顺便就是后端 API 契约
- e2e 测试天然就有

`src/mocks/handlers.ts` 里按 TDD §6.1 的端点写 mock,Claude Code 看到就懂。

### Storybook 可选,不强求

solo 开发开 Storybook 维护成本大于收益。建议:
- 通用组件(Button/Input/Card)在第 1 周顺手写完
- 业务组件直接在页面里写,有重复再抽

### 验收要"对屏" + "对状态"

每屏完成 = ✅ 视觉对齐 mockup + ✅ loading 状态可见 + ✅ empty 状态可见 + ✅ error 状态可见 + ✅ TypeScript 零错误 + ✅ ESLint 零警告。

任务包里都列了,不用记。

---

## 🚨 常见坑(预先告诉你)

1. **shadcn/ui 不是 npm 包,是代码生成器**。`npx shadcn@latest add button` 会把 button.tsx 复制到你仓库,你可以改。CLAUDE.md 里有提醒。
2. **TipTap 比想象中重**。T06 文档结果页用到,提前在第 2 周一开始就 `npm install`。
3. **SSE 在 dev 服务器经常被代理掐**。Vite proxy 配置见 00-bootstrap。
4. **shadcn 的 Drawer 在移动端表现奇怪**。T07 证据链抽屉 desktop only,任务包里写死了。
5. **DesignHandoff 的颜色 token 是 CSS 变量风格**。我把它们转好放在 `tailwind.config.ts` 里,AI 直接写 `bg-bg-card` 就行,不要让它瞎用 `bg-stone-50`。

---

## 📚 已有文档导航(不重复抄)

| 你需要…  | 看哪个 |
|---|---|
| 产品需求、用户旅程、AC | `../PRD_TokenKnows_MVP.md` |
| 技术栈、API、Schema、部署 | `../TDD_TokenKnows_MVP.md` |
| 颜色、字体、组件清单、每屏规格 | `../DesignHandoff_TokenKnows_MVP.md` |
| 像素级视觉参考 | `../mockups/T0X-*.html` (浏览器打开) |
| 给 AI 的高保真截图 | `../figma_handoff/mockups_png/T0X-*.png` |

---

## 🏁 开干

```bash
# 第一步,而且只有这一步
cat 00-bootstrap.md
```

然后照着跑。第 1 天能拿到一个能 `npm run dev` 的仓库。
