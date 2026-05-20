# TaskTechDesign · 15 任务级技术方案

> **定位**：每屏的"工程判断 + 上下游 contract + 已知坑的工程补充"。**不重复任务包内容**，只补任务包之外的工程判断；任务包仍是 Source of Truth。
>
> | 项 | 内容 |
> |---|---|
> | 版本 | v0.1 |
> | 撰写日期 | 2026-05-20 |
> | 上游 | [Architecture.md](./Architecture.md) §10（路由/feature 映射）、[SharedFoundations.md](./SharedFoundations.md)（地基） |
> | 任务包 | [tasks/T01-T15.md](./tasks/) |
> | 排期来源 | [README.md](./README.md) 4 周计划 + [CLAUDE.md](./CLAUDE.md) 推进顺序 |

---

## Part 0 · 文档边界

```
┌──────────────────────────────────────────────────────────────────┐
│ 业务 / 产品                                                       │
│   BRD / PRD / Pitch / DesignHandoff（不在本文档讨论）             │
├──────────────────────────────────────────────────────────────────┤
│ 架构 / 部署 / 复用                                                │
│   Architecture.md（宏观分层 / digital_enterprise 复用 / 双轨）    │
│   ↑ 本文档引用，不重复                                            │
├──────────────────────────────────────────────────────────────────┤
│ 项目地基                                                          │
│   SharedFoundations.md（api / stores / 路由 / token / a11y）      │
│   ↑ 本文档引用 §X 不重复                                          │
├──────────────────────────────────────────────────────────────────┤
│ 任务级深化（**本文档**）                                          │
│   - 每屏的关键工程决策与补充                                       │
│   - 跨任务上下游 contract                                         │
│   - Track A 4 周逐日补强                                          │
│   - 全局质量门禁                                                  │
├──────────────────────────────────────────────────────────────────┤
│ 屏级施工指南                                                      │
│   tasks/T01-T15.md（路由 / API / 组件 / 验收 / 已知陷阱）         │
│   ↑ 由本文档补充而非取代                                          │
└──────────────────────────────────────────────────────────────────┘
```

**关系准则**：
- Architecture.md 改动 → 本文档不动（除非任务级判断需要跟随调整）
- 任务包改动 → 本文档对应 §X 同步评审
- 本文档改动 → 各任务执行时增量参考，**不需要重读** Architecture.md

---

## Part 1 · 施工原则

### 1.1 推进顺序（唯一来源 = CLAUDE.md）

```
T01 → T02 → T03 → T05 → T06 → T07 → T08 → T04 → T09 → T10 → T11 → T12 → T13 → T14 → T15
```

**不跳着做**——前置屏没完成不开后面（数据依赖会塌）。

### 1.2 不可砍 8 屏

`T01 / T02 / T03 / T05 / T06 / T07 / T11 / T12`。任意一个砍掉主链路就跑不通（README §节奏自检 已声明）。

**如果某周延期**：
- W2 文档页（T06）超时 → 牺牲 W4D19 UI 打磨，T06 不能减
- W3 T04/T10 超时 → 砍 T04 + T10 进 v0.2（DEMO 仍能给客户看）
- 全周延期 → 砍 T09，文档"提交"按钮直接进 T11

### 1.3 工作循环（每屏必跑）

```
1. 读任务包 tasks/T0X.md
2. 读 SharedFoundations 引用的节（地基复用）
3. 读 docs/mockups/T0X-*.html 看视觉（必须）
4. 写 MSW handler（在 src/mocks/handlers/<resource>.ts）
5. 写 Page + components + hooks
6. 跑 npm run dev 自测三态（Loading/Empty/Error/Success）
7. tsc + lint 零警告
8. git commit -m "T0X: ..."
```

### 1.4 先 mock 后联调

W1-W3 全程用 MSW。`src/mocks/handlers/<resource>.ts` 既是 mock 也是后端 API 契约——W4D16 联调时只需修类型不匹配。

### 1.5 commit 粒度

**每屏一个 commit**，前缀 `T0X:`。如 `T03: 工作台首页静态版本完成`。**不要在一个 commit 里横跨多屏**（CLAUDE.md 已声明）。

---

## Part 2 · T01-T15 技术方案

> 字段说明：
> - 所有任务都有：**目标 / 路由 / API（核心） / 组件骨架 / shadcn / 关键决策与补充**
> - 中等任务加：**Zustand / QueryKey / 4 态 / 已知坑 / 衔接**
> - 复杂任务再加：**数据流时序 / 并发竞争 / 降级路径**

---

### T01 · 认证流程（简单 · 6 字段）

- **目标**：4 子页（注册 / 登录 / 邮箱验证 / 找回 / 重置密码）。新用户的入口。
- **路由**：`/login` `/register` `/verify-email?token=` `/forgot-password` `/reset-password?token=`。`AuthLayout` 包裹。
- **API**：`POST /auth/register|login|forgot-password|reset-password` `POST /me/verify-email` `GET /me`。详见 [tasks/T01-auth.md](./tasks/T01-auth.md) §4。
- **组件骨架**：`features/auth/{Login,Register,VerifyEmail,ForgotPassword,ResetPassword}Page.tsx` + `components/AuthCard.tsx` + `PasswordInput.tsx`（眼睛切换）。
- **shadcn**：Form / Input / Label / Button / Card / Separator。
- **关键决策与补充**：
  - **zod schema 写在每个 Page 同文件里**，不抽 schemas/。理由：表单 schema 不复用、抽出去反而难定位。验证流程参考 `~/.claude/rules/typescript/patterns.md`。
  - **注册成功不自动登录**（任务包已声明），跳"请验证邮箱"中间页。这是产品决策，**违反它会被 PRD §5.1 拒掉**。
  - 找回密码 token 失效要展示**具体**错误（"已过期 / 已使用 / 无效"），不要笼统"失败"——这是客服 ticket 的高发问题。
  - **不要写"记住我" checkbox**。MVP 用 access token 15min + refresh 7d（refresh 由后端 httpOnly cookie，前端不可见），默认即"记住"。
  - 失败次数后端会 423 lock 15 分钟，**前端在 UI 显式倒计时**而不是 toast——用户能看见才不会狂点。

---

### T02 · 项目创建向导（简单 · 6 字段）

- **目标**：4 步向导建项目 + 接 ≥ 1 个数据源，结束后跳工作台。
- **路由**：`/projects/new` → 完成后跳 `/projects/:id`。
- **API**：`POST /projects` `POST /projects/:id/datasources/{github|local-file}` `GET /projects/:id/datasources`。
- **组件骨架**：`features/projects/NewProjectPage.tsx` + 4 个 Step + 4 个 integration card（ClaudeCode / Cursor / VsCode / GitHub）+ `WizardStepper.tsx`。
- **shadcn**：Card / Input / Textarea / Button / RadioGroup / Tabs / Progress / Badge。
- **关键决策与补充**：
  - **向导 state 用 `useReducer` 不用 Zustand**。状态机有限（4 步 + 选中的数据源），无需跨页持久化；用户中途关掉浏览器再回来就重新开始，**故意不 persist**。
  - **数据源多选支持**（GitHub + Claude Code 同时接），但 Step 3 接入指引每个数据源**独立卡片**展示，不要并排挤一屏。
  - **连接 token 默认遮蔽 + "显示"按钮**——token 是 HMAC 签名的（TDD §8.2），**前端正则校验不可靠**，必须依赖后端验证。
  - **复制 token 按钮加 toast** 确认成功（用户最常见的 confusion 是"复制了吗"）。
  - **项目名重名**（409）要在 Step 1 提交时立刻报错并定位到该字段，**不要让用户走完 4 步才发现**。
  - 中途关闭向导：弹 dialog "确认放弃"，**不要静默丢数据**——4 步走到一半最容易触发"为什么我的数据没了"。

---

### T03 · 工作台首页（中等 · 10 字段）

- **目标**：三栏首屏（项目卡 / 实时事件流 / 本周待办）。每天看到的第一屏。
- **路由**：`/` 或 `/projects/:id`；`AppLayout` 包裹。
- **API**：`GET /projects` `GET /projects/:id` `GET /projects/:id/events?from&to&filters` `GET /projects/:id/stats` `GET /projects/:id/todos`。
- **组件骨架**：`features/workbench/WorkbenchPage.tsx` + `ProjectSwitcher / ProjectStats / EventStream / EventCard / EventFilter / TodoList / EmptyWorkbench`。
- **shadcn**：Card / Badge / Avatar / ScrollArea / Tabs / Skeleton / Tooltip。
- **Zustand**：`useProjectStore`（`currentProjectId / setCurrent`）。切项目时 invalidate 旧项目的 query。
- **QueryKey**：[SharedFoundations §5.3](./SharedFoundations.md#53-15-任务-querykey-完整表) 行 T03。
- **4 态**：
  - Loading：三栏分别用 `LoadingSkeleton variant="workbench"`
  - Empty：无项目 → 大空态 + "新建项目"按钮 → T02；有项目无事件 → 中间栏空态 + "检查数据源" → T13
  - Error：每栏独立 retry button（不要整页错误）
  - Success：事件按"今天/昨天/周三 12月X日"分组
- **已知坑（任务包外补充）**：
  - **MVP 不接 SSE，用 30s polling**（SharedFoundations §5.4 已给配置）。理由：Vite proxy 掐 SSE + MSW SSE 不稳 + 录屏 demo 看不出差异。**SSE 留 TODO 注释**，W4D17 联调日替换。
  - 事件流 ≥ 200 条用 `react-window` 虚拟滚动；MVP 简化版本可只 render 最近 200 条 + "加载更早" infinite query。
  - 切项目时 `queryClient.cancelQueries({ queryKey: ['projects', oldId] })` 取消 in-flight 请求。
  - `EventCard` 4 种 source 不同 icon + 左侧色条（commit 绿 / PR 橙 / chat 蓝 / doc 灰）。
  - 健康度小圆点字段是 `health: 'healthy' | 'degraded' | 'down'`，对应 success / warning / danger 三色 token。
- **衔接**：进入来自 T01；出口 → T04（点事件） / T05（侧栏文档） / T13（侧栏设置）。
- **关键决策与补充**：
  - **不要把"项目切换"做成全屏跳转**——下拉菜单选 + URL 更新即可。全屏跳转 = 全 query 失效 = 加载又看到三栏骨架，体验差。
  - 数字卡（事件总数 / 待审 / 数据源健康）每个都用 `Intl.NumberFormat('zh-CN')` 千分位，悬停 Tooltip 显示明细（按 source / author 拆分）。
  - 实时新事件淡入动画用 `transition-duration:fast` (120ms)，**不要弹跳动画**——产品调性是"专业 / 沉静"，不是消息软件。

---

### T04 · 事件详情抽屉（中等 · 10 字段）

- **目标**：点工作台事件流某条 → 右侧 480px 抽屉展示时间轴 / 元数据 / 跳转。
- **路由**：query string driven `?event=:eventId`；不是独立 page。
- **API**：`GET /events/:eventId`。
- **组件骨架**：`features/events/EventDetailDrawer.tsx` + `EventHeader / EventTimeline / EventMetadata / EventValueScore`。
- **shadcn**：Sheet（右侧 drawer）/ Avatar / Badge / Separator / Tabs。
- **Zustand**：`documentUiStore.eventDrawerOpen / activeEventId` + 同步 URL query。
- **QueryKey**：`['events', eventId]` TTL 5min（事件不变，缓存长一点）。
- **4 态**：Loading 抽屉内骨架 / Empty 不适用 / Error 抽屉内错误 + 关闭按钮 / Success 完整渲染。
- **已知坑**：
  - 同一 drawer 切换不同 event **不要先关再开**——直接换内容（避免动画闪烁）。
  - 时间轴 chat 类事件长文本截断 + 点击展开。
  - 隐私字段（如 chat 含 token）后端字段 `is_private: true`，只显示摘要 + "源已脱敏"标记。
- **衔接**：进入来自 T03；出口 → T06（"跳转生成文档"，若该事件已被纳入生成）或 关闭。
- **关键决策与补充**：
  - **Esc / 遮罩 / X / 删除 `?event=` 都能关**——shadcn Sheet 默认支持前 3，URL 同步需要手动处理：`useEffect` 监听 `searchParams.get('event')`，为 null 时关闭抽屉。
  - 时间轴上下文事件**复用同一 drawer 实例**切换内容，不重新挂载——这样切换不闪烁，跟 Linear / Notion 抽屉手感一致。

---

### T05 · 文档列表（中等 · 10 字段）

- **目标**：项目内"草稿 / 待审 / 已通过 / 已发布"文档总览。
- **路由**：`/projects/:id/documents`。
- **API**：`GET /projects/:id/assets?type=&status=` + `POST /projects/:id/assets/generate`（mutation）。
- **组件骨架**：`features/documents/DocumentListPage.tsx` + `DocumentCard / DocumentFilters / DocumentTypeFilter / GenerateDocButton`。
- **shadcn**：Card / Tabs / Badge / Select / Button / DropdownMenu。
- **Zustand**：无。Filter 走 URL query。
- **QueryKey**：`['projects', id, 'assets', filters]`，filters 字典 stringify 后排序。
- **4 态**：Loading 6 骨架卡 / Empty "还没有文档" + "生成第一份" / Error 整页 retry / Success 3x2 网格。
- **已知坑**：
  - "生成中"卡 polling 进度（每 5s），完成后自动从 cache 移除"生成中"标记。
  - 删除二次确认 dialog（"删除后将无法恢复"）。
  - cursor 分页每页 20。
- **衔接**：进入来自 T03（侧栏）；出口 → T06（点卡）。
- **关键决策与补充**：
  - **"生成新文档"按钮触发 dialog**（**不是**跳到新页面）。dialog 内选类型 + 时间窗 + 源 filter + LLM 模型，提交即返回 asset_id + 关闭 dialog + 文档卡进入"生成中"状态。理由：用户多份并行生成时，跳页 = 容易迷路。
  - 卡片"更多"菜单（复制 / 删除 / 导出）的"复制"是**克隆 asset**（创建新草稿），不是复制链接——避免和"导出/分享"混淆。
  - **状态徽标颜色严格按 token**：draft=warning / reviewing=info / approved=success / published=accent-primary。审批中和已发布是两种语义，**不要用相同色**。

---

### T06 · 文档生成结果页（**复杂 · 13 字段**）

- **目标**：**产品核心卖点**。三栏：左大纲 / 中正文（TipTap）/ 右侧操作。用户读、改、查证据、重生成。
- **路由**：`/projects/:id/documents/:docId`。
- **API**：`GET /assets/:assetId` + `PATCH /assets/:assetId/chapters/:chapterId` + `POST /assets/:assetId/chapters/:chapterId/regenerate` + `POST /assets/:assetId/submit` + `GET /assets/:assetId/chapters/:chapterId/evidence`。
- **组件骨架**：`features/documents/DocumentPage.tsx` + `DocOutline / DocEditor / ChapterBlock / ChapterFooter / InlineEvidence / DocSidebar / DocHeader`。
- **shadcn**：Button / Card / Separator / Tooltip / DropdownMenu / Sheet / Skeleton / ScrollArea。
- **Zustand**：`documentUiStore`（evidenceOpen / regenerateOpen 等）。
- **QueryKey**：`['assets', assetId]` + `['assets', assetId, 'chapters']`。
- **4 态**：Loading 大纲 + 章节 skeleton / Empty 不适用 / Error 整页 + 返回列表 / Saving 顶部"保存中... / 已保存 X 秒前" / 重生成中 章节灰化 + Progress 覆盖。
- **数据流时序**：
  ```
  挂载页面 → useQuery 加载 asset + chapters (并行)
    → 渲染大纲 + IntersectionObserver 监听章节标题
    → TipTap 初始化（每章一个 editor 实例，不共享）
  用户编辑某章节
    → TipTap onUpdate 触发（每按键）
    → lodash.debounce 包装 2s
    → 触发 PATCH chapter
    → 期间：顶部状态"编辑中" → "保存中" → "已保存"
  用户点"重生成此章节"
    → 打开 T08 Dialog（不离开页面）
    → 提交后 → 章节 isPending=true → 章节 footer 显示"生成中"
    → POST /regenerate 返回新章节内容 → setQueryData 更新该章节 → isPending=false
  ```
- **并发竞争**：
  - **自动保存 ↔ 重生成**：重生成期间禁用 TipTap onUpdate 写入（`useChapterMutation.isPending` 时 readOnly）。
  - **多人同时编辑**：MVP 章节级锁定（PRD §5.5 E1）——同一时刻只有 1 个 Editor 真编辑，其他人只读 + 显示 "X 正在编辑"。锁信息通过 SSE 推送（W4D17 联调后），MVP 阶段简化为后端 PATCH 返回 409 时弹"合并 / 覆盖 / 放弃"对话框。
  - **乐观更新关闭**：服务端可能改 content（如格式化），收到 response 必须以服务端为准 reconcile（**不要**先 setQueryData 再发请求）。
- **降级路径**：
  - **保存失败**：草稿留 localStorage（key `tokenknows_draft_{chapterId}`）+ toast 红色"已保存到本地，点重试"。**绝不悄悄丢草稿**。
  - **TipTap 初始化失败**（极少见）：fallback 到 textarea。
  - **网络中断**：进入"离线编辑"模式，本地缓存修改，重连后弹"合并 / 覆盖 / 放弃"。
- **已知坑**：
  - TipTap 的 onUpdate 每按键触发 → 必须 lodash.debounce 2s（任务包已声明，再强调）。
  - 三栏 > 1280px 正常；1024-1280 大纲收成 icon-only；< 1024 右栏移到顶部 collapsible。
  - 长文档（> 20 章节）左大纲有自己的 ScrollArea。
  - 证据角标 `[3]` 点击用 `event.stopPropagation`，否则 TipTap 误以为是文本编辑。
- **衔接**：进入来自 T05；出口 → T07（点 `[3]`）/ T08（章节 footer 重生成）/ T09（提交审批）。
- **关键决策与补充**：
  - **每章一个 TipTap editor 实例**，不要共享。理由：(a) 章节级 readOnly 独立切换；(b) editor 销毁时 useEffect cleanup 不会误销其它章；(c) 重生成单章节时只需替换该 editor 内容。
  - **Evidence mark 用 TipTap 自定义 mark** 而不是 inline component。原因：mark 是数据驱动的标注（character-level span），换 chapter content 时不会丢；自定义 inline component 在 markdown round-trip 时会失语义。
  - **自动保存的"状态机"**在顶栏统一显示，**不要**在每章节单独显示——15 章节就 15 个"已保存"会闪烁。
  - **"提交审批"按钮在 status=draft 时显示**，点击 → 确认 dialog（"提交后将进入审批，期间不可编辑"）→ POST submit → 跳 T09。**不要在所有状态都显示**。

---

### T07 · 证据链抽屉（**复杂 · 13 字段**）

- **目标**：点章节内 `[3]` → 右侧抽屉看证据原始 PR / chat / commit。
- **路由**：T06 内 drawer，可深链 `?evidence=:id`。
- **API**：`GET /assets/:assetId/chapters/:chapterId/evidence`（章节内所有）+ `GET /evidence/:id`（单条详情，可选）。
- **组件骨架**：`features/evidence/EvidenceDrawer.tsx` + `EvidenceHeader / EvidenceSourceCard / EvidenceQuote / EvidenceContext / EvidenceListPanel`。
- **shadcn**：Sheet / Tabs / Card / Badge / Separator。
- **Zustand**：`documentUiStore.evidenceOpen / activeEvidenceId`。
- **QueryKey**：`['assets', assetId, 'chapters', chapterId, 'evidence']`。
- **4 态**：Loading 抽屉骨架 / Empty 章节无证据→提示 / Error retry / Success。
- **数据流时序**：
  ```
  用户点 [3] → InlineEvidence onClick(evidenceId)
    → setActiveEvidenceId + setEvidenceOpen(true)
    → 抽屉打开，顶部列表加载本章证据全集（一次 query）
    → 高亮 activeEvidenceId 项
  切换证据（点列表里另一项）
    → 仅 setActiveEvidenceId（不重开 drawer / 不重 query）
    → 详情区滚动到该项
  ```
- **并发竞争**：
  - 用户在 T06 重生成完一章 → Evidence 可能整体重新生成 → 已打开的抽屉应该自动 invalidate query 并显示新列表，**不要悄悄旧数据**。
  - 用户编辑章节 → Evidence stale 状态（SharedFoundations §未涉及，详见 Architecture.md §6.2）→ 抽屉里 stale 项黄色徽标。
- **降级路径**：
  - 证据来源被脱敏（PRD §5.4 D2）→ 非 Reviewer/Owner 显示遮蔽；Reviewer/Owner 可"临时展开原文"，展开入审计日志。
  - 源事件已物理删除 → 显示"来源已删除"+ 保留最后已知 metadata（PRD §5.4 D2 异常）。
- **已知坑**：
  - 抽屉桌面 480px desktop only；移动端全屏 fallback（任务包已声明）。
  - 证据上下文 ≤ 500 字内联预览 + "展开全文"。
  - 多条 Evidence 指向重叠 span → 按 Event 分组，可折叠。
- **衔接**：进入来自 T06（章节内 `[3]`）；出口 → T04（点"在事件流中查看"）/ 外链（点"在源头打开"）。
- **关键决策与补充**：
  - **抽屉里 listed evidences 用同一 useQuery**，不要每点一条新建一个 detail query。证据数据在章节级是闭包的（PRD §5.4），抽屉打开时一把拉全。
  - **trust_score 分项细解可选展开**——默认显示总分，悬停 / 点击展开 source_authority / corroboration / recency / extraction_confidence 四项。Reviewer 关心细解；Editor 看总分就够。
  - **"在源头打开"用 `<a href target="_blank" rel="noopener noreferrer">`** 而不是 `window.open`。安全 + a11y + 用户惯性。

---

### T08 · 重生成对话框（中等 · 10 字段）

- **目标**：章节重生成；调 prompt + 切 LLM 模型。
- **路由**：T06 内 Modal。
- **API**：`POST /assets/:assetId/chapters/:chapterId/regenerate` + `GET /projects/:id/llm/models`（allowlist）。
- **组件骨架**：`features/generation/RegenerateDialog.tsx` + `ModelSelector / InstructionEditor / ContextPreview`。
- **shadcn**：Dialog / RadioGroup / Textarea / Button / Select / Card / Badge。
- **Zustand**：`documentUiStore.regenerateOpen / regenerateChapterId`。
- **QueryKey**：`['projects', id, 'llm', 'models']` TTL 5min。
- **4 态**：Loading 按钮 spinner / Empty 无可用模型→提示去 T14 / Error 行级红字 / Success 关 dialog + 章节进入 loading。
- **已知坑**：
  - 模型 allowlist 由 T14 配置，前端只列后端返回的可用模型。**不要硬编码模型名**。
  - "本地模型"未配置时**显示但 disabled** + Tooltip 提示——让用户知道有这个选项但需配置。
  - prompt 模板文案**硬编码在前端**（如"更口语化"），不需要后端管。
- **衔接**：进入来自 T06 章节 footer；出口 → 回 T06（章节进入 loading）。
- **关键决策与补充**：
  - **`dry-run preview` 按钮在模型卡上**——按下不真调云端，返回 "如果开启会发哪些字段 / 哪个 provider"。这个端点 TDD §7 没有，需要后端补一个轻量的 `POST /llm/preview`。**架构红线**：永不应出现"用户以为没出域，其实出了"的状态。
  - 上下文预览（这次会带入哪些 ValueSegment）**默认折叠**——多数用户不关心，但"看穿黑盒"是产品差异化卖点。
  - 提交按钮 disabled 直到 instruction 不为空（任务包要求），同时**模型必须选中**——MVP 阶段不提供"用默认模型"按钮（避免用户漏选）。

---

### T09 · 审批视图（**复杂 · 13 字段**）

- **目标**：Reviewer 章节级 approve / reject + 批注。
- **路由**：`/projects/:id/documents/:docId/review`。`RequireRole role="reviewer"`。
- **API**：`GET /assets/:assetId` + `POST /assets/:assetId/chapters/:chapterId/approve|reject` + `POST /assets/:assetId/comments`。
- **组件骨架**：`features/review/ReviewPage.tsx` + `ReviewSidebar / ChapterApprovalRow / CommentThread / BottomActionBar`。
- **shadcn**：Button / Textarea / Badge / Card / Dialog（退回原因）/ Tooltip。
- **Zustand**：本页临时 state 用 useState；批注草稿（未提交）用 useState 本地，**不**走 Zustand。
- **QueryKey**：与 T06 共享 `['assets', assetId]`，但本页 readOnly。
- **4 态**：Loading 三栏骨架 / Empty 不适用 / Error / Approved/Rejected 章节左侧色条变色。
- **数据流时序**：
  ```
  Reviewer 打开 → 加载 asset + chapters + 已有 comments + 已有 approval state
    → 判断角色（前端 RequireRole 拦截 + 后端再校验）
    → 章节级 readOnly 渲染（markdown-it 或 TipTap readOnly mode）
  Reviewer 选中文档片段
    → 浮出"批注"按钮 → 弹评论框
    → 提交 comment → POST comments → invalidate ['assets', assetId, 'comments']
  Reviewer 章节级 approve
    → 立即 POST approve → setQueryData 该 chapter.approval_state = approved
    → BottomActionBar 进度更新（N/M）
  全部 approved + 脱敏全 confirmed
    → "进入发布"按钮激活 → 弹 dialog 确认 → 跳 T11
  ```
- **并发竞争**：
  - Editor 同时在 T06 改章节（产品决策禁止：进入 review 后章节锁，PRD §5.5 E2）→ 后端拒绝 → 前端显示"该文档审批中，编辑已禁用"。
  - 多 Reviewer 同时审：MVP 不做实时同步，**最后写的覆盖**——审批结果是 idempotent 字段（approved / rejected），最后写的胜出，前端简单 invalidate 即可。
- **降级路径**：
  - Reviewer 48h 无响应（PRD §5.5 E2 异常）→ 通知 Owner 可"代行批准"。前端在 BottomActionBar 显示"Reviewer 长时间未响应（X 小时）"提示，但**代行批准的 UI** 由 Owner 在 T13 项目设置触发（不在 T09 内）。
  - 退回不删除批注——下一轮 T06 的 Editor 看得到。
- **已知坑**：
  - **左侧文档 readOnly**——不可用 TipTap 编辑模式，用 markdown-it 渲染 + DOM 选择监听 + 浮按钮。
  - 批注 span 锚点基于 **章节 ID + 字符偏移**，不要基于 DOM 节点（DOM 改了批注就漂走）。
  - "全部通过"按钮在所有章节都 approved 之后才启用。
  - "退回原因"必填 + 字符 ≥ 10——避免空退回。
- **衔接**：进入来自 T05（status=reviewing）或工作台待办；出口 → T11（全通过 + 脱敏完成）或 T06（退回，附评论）。
- **关键决策与补充**：
  - **三层批注（行级 / 章节级 / 文档级）UI 视觉分层**——行级显示在批注侧栏的对应章节内，章节级在章节标题下，文档级在 ReviewSidebar 底部。**不要全部混在一个列表**——Reviewer 很难找。
  - **"展开所有未读批注"快捷键**（Cmd+Shift+A）+ 顶部按钮：Reviewer 有时只关心 unresolved → 一键展开看完。
  - **每个章节的左侧色条状态**视觉上独立：pending=灰 / approved=success / rejected=danger。这样 Reviewer 在大纲一眼能看到进度。

---

### T10 · 脱敏面板（**复杂 · 13 字段**）

- **目标**：发布前自动扫描敏感项，逐条确认 / 豁免。
- **路由**：`/projects/:id/documents/:docId/redaction`。从 T06 顶部"提交审批"前置或 T11 发布对话框前置。
- **API**：`POST /assets/:assetId/redaction/scan` (异步返 job_id) + `GET /assets/:assetId/redaction/scan?job_id=` (polling) + `POST /assets/:assetId/redaction/confirm|exempt`。
- **组件骨架**：`features/redaction/RedactionPage.tsx` + `ScanProgress / ItemList / ItemCard / ExemptDialog / BulkActionBar`。
- **shadcn**：Card / Checkbox / Badge / Button / Dialog / Progress / Tabs。
- **Zustand**：本页 useState（job_id / 选中项 Set）。
- **QueryKey**：`['assets', assetId, 'redaction', { jobId }]` `refetchInterval` 2s 直到 done。
- **4 态**：
  - Loading：扫描中 Progress + "正在扫描 X 个章节"
  - Empty：无命中 → 绿色"无敏感内容，可直接发布" + "进入发布"按钮
  - Error：扫描失败 + 重新扫描
  - Success：分组列表 + 底部操作
- **数据流时序**：
  ```
  挂载 → 看是否已有 scan 结果（cache 命中或最近 scan 状态）
    → 没有则 POST scan → 返回 job_id → 进入 polling
  polling 每 2s GET /redaction/scan?job_id
    → 状态 status=pending|running|done|failed
    → done 时停止 polling（refetchInterval (q) => q.data.status === 'done' ? false : 2000）
    → 渲染 items[]（分组 PII / 密钥 / 内部代号 / 自定义）
  用户单项操作（脱敏/豁免）
    → 即时 POST confirm|exempt
    → 该 item 移到"已处理"tab
  用户批量
    → 选中后 BulkActionBar 出现 → 一键 POST confirms
  全部处理完
    → "进入发布"按钮高亮 → 跳 T11
  ```
- **并发竞争**：
  - 用户 polling 时关闭页面：cleanup `queryClient.cancelQueries`。
  - 用户在另一个 tab 修改了文档章节 → 当前 tab 的 scan 结果 stale → 用户回到本 tab 时 useFocusEffect 触发 invalidate + 自动重 scan。
- **降级路径**：
  - LLM 不可用（PRD §5.6 F1）→ 自动降级为仅规则层 + UI 显式提示 "部分语义敏感项未识别，请人工审查"。
  - scan job timeout（> 60s）→ 显示"扫描超时" + 重新扫描按钮。
  - 私有化场景关出域且本地模型挂 → 用本地小模型做 LLM 层（性能降但不阻断），UI 标"使用本地模型"。
- **已知坑**：
  - **脱敏替换文本配置化**（在 T13 项目设置改），前端 `[REDACTED]` 不能写死——读 `project.custom_redaction_terms.replacement_template`。
  - 豁免理由必填 + 进审计日志（T14 看）。
  - 同一文档内同样字符串只算一项，不重复（后端 dedupe）。
  - 大文档（> 50k 字）分段处理 + 显示进度。
- **衔接**：进入来自 T06 / T11；出口 → T11（全部处理后）或 T06（用户中途返回）。
- **关键决策与补充**：
  - **scan 是**幂等**的**——重新打开页面 / 刷新 → 后端检查现有 scan 是否 stale（asset.updated_at > scan.created_at？），stale 自动重扫描，否则复用。**前端不要把重扫做成"按钮"**——让产品自动决策。
  - **类型化占位符**（`[CUSTOMER]` / `[API_KEY]` / `[INTERNAL_SYSTEM]`）默认使用，**用户可改文本但不可改类型**——保持审计一致性。
  - **"已处理"tab 默认折叠**——典型用户先看 pending 处理完，再翻已处理验证。
  - **撤销栈**：最近 20 步 confirm/exempt 可撤销（Cmd+Z 触发）——避免误点导致返工。

---

### T11 · 发布对话框（中等 · 10 字段）

- **目标**：选渠道（站内 / 公开链接 / 导出）+ 确认 → 触发发布 → 跳 T12。
- **路由**：从 T06 / T09 / T10 触发的 Modal。
- **API**：`POST /assets/:assetId/publish` body `{destinations[], publish_mode}` + `POST /assets/:assetId/export` body `{format}`。
- **组件骨架**：`features/publish/PublishDialog.tsx` + `DestinationSelector / VisibilityPicker / ExpiryPicker / ConfirmChecklist`。
- **shadcn**：Dialog / Checkbox / RadioGroup / Select / Button / Card / Tooltip。
- **Zustand**：本地 form state（useState）。
- **QueryKey**：无（mutation）。
- **4 态**：Loading 发布中 spinner / Empty 不适用 / Error dialog 内行级 + toast / Success 关 dialog + 跳 T12。
- **已知坑**：
  - **公开链接 URL = unguessable token**（后端生成），前端不要尝试预测。
  - 导出 PDF 后端渲染慢，长 timeout (60s) + 显式加载状态。
  - "导出文件"和"在线发布"可同时选，后端独立处理。
- **衔接**：进入来自 T06 / T09 / T10；出口 → T12（成功）。
- **关键决策与补充**：
  - **"上次记住"**：用 localStorage（key `tokenknows_publish_last_destinations_{projectId}`）记上次勾选的 destinations + visibility，下次默认勾上（PRD 要素 #15）。
  - **Confirm checklist 三项**："已完成脱敏 / 审批已通过 / 了解公开后不可撤销 PII"——全勾 submit 才启用。**不要**简化成单 checkbox——发布是高风险动作，三次确认值得。
  - **发布按钮 disabled 状态显式 Tooltip**——"还有 N 处未脱敏" / "审批未通过"具体哪一条挡着，让用户能立刻定位。

---

### T12 · 发布回执（中等 · 10 字段）

- **目标**：发布成功后展示版本号 + 各渠道链接 + 与上版本 diff。
- **路由**：`/projects/:id/documents/:docId/published/:publishId`。
- **API**：`GET /publish-records/:id` + `GET /assets/:assetId/versions/:v1/diff?to=:v2` + `POST /publish-records/:id/revoke`。
- **组件骨架**：`features/publish/PublishReceiptPage.tsx` + `ReceiptHeader / DestinationList / VersionDiff / RevokeDialog`。
- **shadcn**：Card / Badge / Button / Tabs / Dialog / Tooltip。**diff 渲染**用 `diff` npm 包（W4D15 安装：`npm i diff @types/diff`）。
- **Zustand**：无。
- **QueryKey**：`['publish-records', publishId]` + `['assets', assetId, 'versions', v1, 'diff', v2]`。
- **4 态**：Loading 整页骨架 / Empty 不适用 / Error 跳回文档页 / Success 完整渲染。
- **已知坑**：
  - 撤回不可逆，dialog 强提示。
  - 多渠道异步部分成功，逐项展示状态（success / failed / pending）。
  - diff 数据量大用 lazy expand（默认展开 1 章节）。
- **衔接**：进入来自 T11；出口 → T05 文档列表 / T06 文档页。
- **关键决策与补充**：
  - **diff 计算放 Web Worker**——`diff` lib 大文档（> 5000 行）会卡 UI 线程。worker 内跑完返回 spans，主线程渲染 `<mark>`。
  - **"复制公开链接"按钮 + toast 确认**——发布回执最高频动作之一。
  - **撤回按钮位置**：page footer 而不是 header，避免误点。撤回后页面状态变红"已撤回"+ 所有渠道链接置灰，**不删页面**——版本历史保留。

---

### T13 · 项目设置（简单 · 6 字段 · v0.2）

- **目标**：项目基本信息 / 成员 / 数据源 / 脱敏规则 / 删除。
- **路由**：`/projects/:id/settings/{info|members|datasources|redaction-rules}`。
- **API**：`PATCH /projects/:id` + `DELETE /projects/:id` + `GET/POST/PATCH/DELETE /projects/:id/members` + `GET/DELETE /projects/:id/datasources/:dsId` + 自定义规则 CRUD。
- **组件骨架**：`features/settings/ProjectSettingsPage.tsx` + 4 个 Tab + `DangerZone / InviteMemberDialog`。
- **shadcn**：Tabs / Card / Table / Input / Button / Dialog / Badge / Switch / Select / Textarea。
- **关键决策与补充**：
  - **当前 tab 走 URL**（不是 useState），刷新保留位置。
  - **DangerZone 删除项目**：必须用户**输入项目名确认**（不是单点 OK）——典型 high-impact 二次确认模式。
  - **不能把自己从项目里删**——UI 上隐藏自己那行的"删除"。
  - **正则规则测试输入框**：用户输入正则 → 实时高亮匹配（debounce 300ms，避免每键 invoke）。无效正则显示行级红字（`try { new RegExp(input) } catch`）。
  - **数据源健康检查**慢但要可见——按钮"检查健康"独立按钮，显示 spinner + 上次检查时间。**不**自动 polling 健康——用户驱动。

---

### T14 · LLM 出域（**复杂 · 13 字段 · v0.2**）

- **目标**：配置项目允许的 LLM 模型 + 三层出域开关 + 出域审计日志。
- **路由**：`/projects/:id/settings/llm-egress` 或 `/admin/llm`。
- **API**：`GET/PATCH /projects/:id/llm-config` + `GET /egress-log?project_id=`。**架构红线追加**：`POST /llm/egress/preview`（dry-run，TDD §7 未列，需后端补）。
- **组件骨架**：`features/admin/LlmEgressPage.tsx` + `ModelAllowlist / EgressToggle / AuditLevelPicker / EgressLogTable`。
- **shadcn**：Switch / Card / Badge / Table / Select / Dialog。
- **Zustand**：无。
- **QueryKey**：`['projects', id, 'llm-config']` + `['egress-log', filters]`。
- **4 态**：Loading 配置加载骨架 / Empty 出域日志空 → "近期无出域记录" / Error retry / Success 保存后 toast。
- **数据流时序**：
  ```
  挂载 → 加载 llm-config + 最近 100 条 egress_log
    → 三层 toggle 渲染当前状态：instance / project / task[]
  用户调整 toggle（例：开启 weekly_report 出域 → Anthropic）
    → 立即弹 dry-run preview dialog
    → "如果开启，将向 Anthropic 发送：模型 / token 数 / 字段类型 ..."
    → 确认后才真 PATCH config
  用户保存
    → PATCH /llm-config → invalidate 相关 query
    → toast "已保存"
  ```
- **并发竞争**：
  - 实例管理员同时改 instance_egress_enabled → 项目级 / 任务级 UI 实时反应（read-after-write）。
  - 出域开关变更**立即生效**（后端 FastAPI 中间件读 cache 即可），不要等用户重新登录。
- **降级路径**：
  - 全关情况下，T08 重生成对话框的"模型选择"只列本地模型 + 标 "已关闭云端出域"。
  - 关闭出域时弹 dialog 警示 "将无法使用云端 LLM"，二次确认。
- **已知坑**：
  - 模型 allowlist 改动后，**主动 invalidate** T08 的 `['projects', id, 'llm', 'models']` query——否则用户在 T08 看到旧列表。
  - audit_level=full 时显示"查看详情"展开**脱敏后**的 prompt（不是原文）。
  - 日志默认 7 天 + "加载更早" cursor 分页。
- **衔接**：进入来自 T13 项目设置 / T15 admin；出口 → 保存留页。
- **关键决策与补充**：
  - **dry-run preview 是产品差异化卖点**（PRD §6.7 / Pitch §5）——用户能"看穿"出域行为是 TokenKnows 与 Notion AI / Glean 的核心差异。这个 UI 必须在主流程上而不是隐藏菜单。
  - **三层 toggle 视觉层级**：instance（外层卡片，深色边） → project（中层） → task[]（每 task 一行）——视觉嵌套体现"任一层关，全链路关"。
  - **关闭出域**比开启需要更强确认——开启时一句话 dialog，关闭时显式列出"将影响哪些 task / 哪些模型不可用"。

---

### T15 · 实例管理员控制台（简单 · 6 字段 · v0.2）

- **目标**：实例总览（用户 / 项目 / 配额 / 审计）。
- **路由**：`/admin/{stats|users|quotas|audit}`。
- **API**：`GET /admin/stats|users|projects|quotas` + `GET /audit-log` + `PATCH /admin/quotas/:id`。
- **组件骨架**：`features/admin/{AdminStatsPage,AdminUsersPage,AdminQuotasPage,AdminAuditPage}.tsx` + `AdminLayout` + `StatCard / UserRow / QuotaBar / AuditFilters`。
- **shadcn**：Card / Table / Badge / Button / Progress / Input / Select / DropdownMenu。**recharts** 用于 stats 图表（W4D15 安装：`npm i recharts`）。
- **关键决策与补充**：
  - **AdminLayout 深色 header**（`bg-inverse-bg text-inverse-text`）——视觉上与业务屏分明，**误进的用户立刻知道这里是 admin 区**。
  - 配额 80% 显示橙色，100% 红色——遵循经典阈值。
  - **审计日志导出 CSV** 按钮在 page header——是合规审查最高频动作。
  - **修改配额 dialog 二次确认 + 进 admin 自己的 audit log**——管理员的操作也要被记录。
  - **整页权限**：`RequireAuth + RequireRole role="instance_admin"`，前端拦截 + 后端校验双重。

---

## Part 3 · 跨任务衔接 contract

| 任务 | 上游传入 | 出口去向 | Contract（数据形态） |
|---|---|---|---|
| T01 | URL `?redirect=path` | / 或 redirect | `authStore.setAuth(user, token)` |
| T02 | / 工作台 | `/projects/:id` | 新建后 invalidate `['projects']` + `projectStore.setCurrent(id)` |
| T03 | `/` 或 `/projects/:id` | T04 / T05 | URL `?event=:id` 触发 T04 / 侧栏链接 T05 |
| T04 | URL `?event=:id` from T03 | T06（"跳转生成文档"） | drawer 内点击 → `navigate('/projects/.../documents/' + asset.id + '#chapter-' + ch.id)` |
| T05 | / 工作台侧栏 | T06 | 卡片点击 → `navigate('/projects/.../documents/:docId')` |
| T06 | from T05 | T07 / T08 / T09 | `documentUiStore` 各 action 触发；提交审批 → `navigate(.../review)` |
| T07 | T06 内 `[3]` click | T04 / 外链 | `documentUiStore.openEvidence(id)` |
| T08 | T06 内 footer "重生成" | 关闭 dialog + 章节 isPending | mutation 响应 → setQueryData |
| T09 | from T05 或工作台待办 | T11 或 T06 | "全部通过" → `navigate(.../redaction)` → T11；"退回" → POST + `navigate(.../documents/:docId)` |
| T10 | from T06 顶部或 T11 前置 | T11 | 全 confirm → `navigate(.../publish)` |
| T11 | from T06 / T09 / T10 | T12 | POST publish 响应 → `navigate('/published/' + publishId)` |
| T12 | from T11 | / 或 T05 / T06 | revoke 操作就地 |
| T13 | 工作台项目菜单 | 自身 tabs | tab 走 URL |
| T14 | T13 / T15 | 自身 | 改 LLM config → invalidate T08 `['llm', 'models']` |
| T15 | 头像下拉 | 自身 | 不影响其它任务 |

---

## Part 4 · Track A 4 周逐日补强（W1-W4 共 20 天）

> 此部分**只补 README 没说的颗粒**：每天的"先做什么 / 后做什么"次序、与 SharedFoundations 节的对应、卡壳降级。
>
> README 的"哪一天做哪屏"维持权威；本节是"那一天怎么做"。

### W1 · 地基 + 进得来（D1-D5）

**D1 · 地基日**（README "路由 + AppLayout 骨架 + 通用 EmptyState/ErrorState/Skeleton" 6h，**这里拆细**）

| 时段 | 任务 | 引用 |
|---|---|---|
| 上午 1h | 修 `index.css` token bug + 加 fontsource | SharedFoundations §8 |
| 上午 1h | 写 `src/lib/api.ts` | SharedFoundations §2 |
| 上午 2h | 写 `src/components/shared/{Empty,Error}State.tsx` + `LoadingSkeleton.tsx` 6 variants | SharedFoundations §3 |
| 下午 1.5h | 写 `src/stores/*.ts` 4 个 store | SharedFoundations §4 |
| 下午 1.5h | 写 `src/types/api.ts` DTOs（按 TDD §6.1 + §5） | TDD |
| 下午 1.5h | 写 `AuthLayout / AppLayout / AdminLayout` + 重构 `src/routes/index.tsx` lazy + guards | SharedFoundations §7 |
| 下午 0.5h | 写 `mocks/handlers/auth.ts` + `me` | SharedFoundations §6 |
| 验收 | `npm run dev` → / 显示 token 验证页（陶土橙 + Lora）；localStorage 见 authStore 占位 | — |
| **卡壳降级** | 如果 D1 没干完到第 7 项（Layout / 路由），D2 不要碰 T01，先把 D1 收尾——**地基没好不要往上盖** | — |

**D2 · T01 认证**（README 7h）

| 顺序 | 子任务 |
|---|---|
| 1 | LoginPage（最简单 → 跑通 useLogin + authStore 链路） |
| 2 | RegisterPage（加 zod 校验） |
| 3 | VerifyEmailPage（URL token 自动 POST） |
| 4 | ForgotPasswordPage |
| 5 | ResetPasswordPage |
| 6 | 测 redirect 链路（未登录访 / → /login?redirect=/） |

卡壳降级：5 个子页跑不完，砍 VerifyEmailPage（W4 联调日补）；D3 不要因 T01 不完整而推后。

**D3-D4 · T02 项目向导**

- D3：Step 1（基本信息） + Step 2（数据源选择 4 卡片）
- D4：Step 3（4 个接入指引 cards） + Step 4（完成页）
- 子任务次序：先把"4 步可前进后退 + 保留数据" state machine 写完，再装饰每步的内容。
- 卡壳降级：4 个接入卡片只完成 Claude Code + GitHub 即可（其它 2 个先 placeholder）。

**D5 · T03 工作台**（README 8h，**这里强调次序**）

| 时段 | 子任务 |
|---|---|
| 上午 2h | 三栏布局静态（假数据 hard-code） |
| 上午 2h | 接 MSW handler `/projects` + `/projects/:id/events` |
| 下午 2h | EventCard 4 种 source 样式 + 时间分组 |
| 下午 2h | polling + 状态联动（健康度 / 数字卡 Tooltip / 切项目） |
| **必须**留 TODO | `// TODO(W4D17): replace polling with SSE` | SharedFoundations §5.4 |

**M1 里程碑 W1 周五验收**：注册 → 建项目 → 看工作台（30s polling），录屏 demo。

### W2 · 文档生成核心环路（D6-D10）

**D6 · T05 文档列表**（6h）：先列表 + 筛选，再"生成新文档"按钮 + dialog。

**D7-D8 · T06 文档页**（核心，**留 1.5 天专门给它**）

- D7 上午 2h：三栏布局静态 + DocHeader / DocSidebar 骨架
- D7 下午 4h：左侧大纲 + IntersectionObserver 联动 + 静态章节渲染（markdown-it，不上 TipTap）
- D7 晚间 / D8 上午 4h：TipTap 接入（每章一个 editor）+ 自动保存 hook（lodash.debounce 2s）
- D8 下午 3h：状态机（编辑中 / 保存中 / 已保存 / 保存失败 + localStorage 兜底）
- D8 晚间 1h：模型徽标 / 状态徽标 / 提交审批按钮（dialog 占位，T09 在 W3 完成）

**D9 · T07 证据抽屉**（7h）：先抽屉静态 + 列表，再角标联动 + 切换证据不重开 drawer。

**D10 · T08 重生成对话框**（6h）：先 dialog form，再 mutation + 章节 loading 状态显示。

**M2 里程碑 W2 周五验收**：打开 mock 文档 → 改章节 → 看证据 → 重生成。**这是给客户看的"魔法时刻"**。

### W3 · 协作 + 合规 + 发布（D11-D15）

**D11 · T04 事件详情**（5h）：drawer 静态 + URL query 同步 + 时间轴切换 drawer 内容。

**D12 · T09 审批**（8h）：先 readOnly 渲染 + 章节级 approve/reject，再批注 thread（行级 / 章节级 / 文档级）。

**D13 · T10 脱敏**（7h）：先 polling scan + 列表，再单/批量操作 + 撤销栈。

**D14 · T11 发布**（6h）：dialog + 渠道多选 + Confirm checklist + 导出文件下载（mock 返回 dummy URL）。

**D15 · T12 发布回执**（7h）：先头部 + 渠道列表 + 复制链接，再 diff 视图（用 `diff` npm 包，**Web Worker 不必在 mock 阶段做**）。

**M3 里程碑 W3 周五验收**：一篇文档完整闭环 T06 → T09 → T10 → T11 → T12 走通，30 分钟内。**这就是 v0.1 MVP**。

### W4 · 联调 + 打磨（D16-D20）

**D16 · 后端联调**（8h）：

- 上午：搭后端骨架（按 Architecture.md §17.1 复制 DE 的 8 个动作）+ pyproject + alembic init + 跑 `uvicorn app.main:app --reload`
- 下午：替换 MSW handlers 为真实 API。**按 SharedFoundations §6.1 文件组织**，逐 resource 关闭 MSW handler 同时打开后端实现，**不要一刀切全关 MSW**——出问题难定位。
- 卡壳降级：联调超 1 天 → e2e (D18) 简化为 vitest + happy-dom 跑 hook 单测（README 已声明）。

**D17 · SSE 替换 polling**（6h）：

- T03 工作台事件流（最高 ROI）
- T06 章节锁定通知（如果还有时间）
- T10 redaction job 进度（如果还有时间，否则继续 polling 也行）

**D18 · Playwright E2E**（6h）：

```typescript
// tests/e2e/main-flow.spec.ts
test('完整主链路 - 注册到发布', async ({ page }) => {
  // 1. 注册
  await page.goto('/register')
  await page.fill('[name=email]', 'demo@example.com')
  // ...
  // 2. 验证邮箱（直接跳，mock token）
  // 3. 建项目
  await page.goto('/projects/new')
  // ...
  // 4. 生成文档（mock data）
  // 5. 编辑 + 看证据 + 重生成
  // 6. 提交审批
  // 7. 通过审批
  // 8. 脱敏确认
  // 9. 发布
  // 10. 看回执
})
```

骨架在 SharedFoundations §13（如果未来扩，补在那里）。

**D19 · UI 打磨**（7h）：

- 对 mockup HTML 逐屏 review 视觉偏差
- a11y 检查（SharedFoundations §11 4 条硬指标）
- 包体积守门（SharedFoundations §12.4）

**D20 · Buffer + 录 demo**（8h）：

- 修最后 bug
- 5 分钟演示视频
- 装一台演示环境

**M-A1 里程碑 W4 周末**：v0.1 演示版上线候选，3 分钟从零走完全链路。

---

## Part 5 · Track B 转轨触发条件（附录）

**何时启动 Track B**：

1. Track A W4D20 完成后**签到 ≥ 1 家试点客户**
2. 客户明确表达"需要私有化部署 / 真实使用"

**怎么切**：

1. W5 起后端骨架在 W2 末已搭（D1 复用 DE 的 core 模块），可直接进入 PRD §11 S3 后端业务逻辑（不必从 S1 起）
2. Track A 4 周相当于前置完成了 Track B 的 S1 + S2 + S3 前端部分
3. Track B 维持 12 周总时长，但内部 Sprint 调整为：
   - S1' (W5-W6) = 后端业务（价值识别 + 文档生成流水线 + 证据链 v1） + 前端补真 SSE / 真错态
   - S2' (W7-W8) = 单级审批后端 + **Ollama 适配器**（M2 gate）→ 首家试点接入
   - S3' (W9-W10) = 双层脱敏 + 4 渠道发布 + 模板齐套
   - S4' (W11-W12) = Cursor / VS Code 扩展 + K8s Helm Chart + 性能 / 安全扫描 → M3 v1.0

**详细 Sprint 内容**：维持 [Architecture.md §15.2](./Architecture.md#152-track-b--试点版12-周--全栈--真私有化) 不变。本文档不重复。

---

## Part 6 · 全局质量门禁

### 6.1 每周里程碑 5 项硬指标

| 项 | 工具 | 阈值 |
|---|---|---|
| TypeScript 类型 | `npx tsc --noEmit` | 0 error |
| Lint | `npm run lint` | 0 warning（CI 阶段 0 error） |
| 视觉对齐 | 人工对 mockup HTML | ≥ 95% 对齐 |
| 三态完备 | 每屏验收 4 态 | 100% 屏 |
| 包体积 | `npm run build` | 主 chunk ≤ 250KB gzip |

### 6.2 上线候选自检清单（W4D20 跑）

```
□ 完整主链路 E2E 通过（Playwright 脚本，D18）
□ 三态全覆盖（grep -r EmptyState src/features | wc -l ≥ 屏数）
□ 无 console.log（grep -r "console.log" src/ 在生产 build 中）
□ 路由守卫 RequireAuth 在所有 / 路由
□ SSE / polling 替换标记 100% 清掉或加 W4D17 验收注释
□ MSW handlers 在生产 build 中关闭（main.tsx 已判断 import.meta.env.DEV）
□ localStorage key 命名一致（tokenknows_*）
□ 包体积守门
□ 5 分钟 demo 视频成片可发客户
□ docker 部署本地验证（一台演示机）
```

### 6.3 Playwright 主链路 E2E 骨架

文件位置：`tests/e2e/main-flow.spec.ts`（D18 写）。骨架在 [Part 4 D18](#d18--playwright-e2e6h) 已给。

依赖 SharedFoundations §7 的路由表——任何路由改动需要同步改 E2E。

---

## Part 7 · 任务级新增风险（架构级见 Architecture.md §16）

| 任务 | 风险 | 缓解 |
|---|---|---|
| T01 | refresh token 不实现 → 用户 15min 后被踢出 | 接受（MVP 决策），观察客户反馈 |
| T02 | 4 步向导用户中途关闭丢数据 | 关闭前弹"确认放弃"dialog（已在关键决策） |
| T03 | 30s polling 在录屏 demo 时观感"慢" | 录屏前手动 invalidate query 一次让事件流"刷新"出现 |
| T05 | "生成中"状态 polling 漏改 → 用户看不到完成 | useFocusEffect 回 tab 时强制 invalidate |
| T06 | TipTap 自动保存与重生成并发 | useState `isPending` 互斥（已在关键决策） |
| T06 | 多人同时编辑 → 409 处理用户体验差 | MVP 弹"合并 / 覆盖 / 放弃"对话框（已在 Track B 复杂化为 SSE 实时） |
| T07 | 证据 stale 状态用户没注意 → 误信旧引用 | 黄色徽标 + Tooltip 解释 stale 含义 |
| T08 | 用户不知道当前用什么模型 | 章节顶部小标永远显示当前模型（已在 PRD 要素 #11） |
| T09 | Reviewer 角色权限前端检查可被绕过 | 后端二次校验是必须的，前端只是 UX 提示 |
| T10 | scan job 超时 60s | 显式提示 + 重新扫描；MVP 不做分段递交 |
| T11 | 公开链接生成后泄露 | 后端用 unguessable token + 可设过期（Pitch §5.6 已提）|
| T12 | diff 大文档卡 UI | Web Worker 计算 |
| T13 | 删除项目误操作 | 输入项目名二次确认 |
| T14 | dry-run preview 端点 TDD 没有 | **后端必须补**，否则架构红线被破 |
| T15 | admin 配额改错 | dialog 二次确认 + 自身 audit log |

---

## 附录 A · 文档更新与同步策略

- **本文档**：每个任务执行完，回填该任务的"关键决策与补充"中实际踩到的坑（替换或追加）
- **任务包** (`tasks/T0X.md`)：完成后**只动验收清单 / 已知陷阱**，不动主结构
- **SharedFoundations.md**：基础设施定型后稳定；**绝不**因单任务需求改动
- **Architecture.md**：架构铁律稳定；**仅**架构级决策变更时改 v0.2 / v0.3
- **README.md**：4 周排期是 ground truth，**不要**因延期改它——改的是本文档 Part 4 的卡壳降级

---

## 附录 B · 与外部 / 上游依赖的接触面

| 任务 | 外部依赖 | MVP 处理 |
|---|---|---|
| T01 | SMTP（邮箱验证 / 找回） | 后端 mock；试点阶段切真实 SMTP |
| T02 | GitHub API（PAT 校验） | mock；联调日切真实 |
| T06 | TipTap 升级（v3 → v4 可能 breaking） | pin 在 v3.x，破坏性升级延到 Phase 2 |
| T08 | LiteLLM 模型列表 | T14 配置驱动 |
| T11 | 飞书 / Slack / Notion OAuth + API | S5 实现至少 1 个；MVP 演示版 mock 全部 |
| T12 | `diff` lib | npm install at W4D15 |
| T15 | recharts | npm install at W4D15 |

---

## 版本历史

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v0.1 | 2026-05-20 | 初稿：7 Part + 任务级深化 + 逐日补强 + 风险登记 | John + Claude |
