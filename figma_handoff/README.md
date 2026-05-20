# TokenKnows MVP — Figma 交付包 (Designer Handoff)

给设计师精修的 15 个 MVP 屏幕。所有素材已就绪,按下面步骤导入 Figma 即可开工。

---

## 1. 这里有什么

```
figma_handoff/
├── README.md                          ← 你正在看的文件
├── mockups_png/                       ← 16 张 2x 高清截图 (Retina)
│   ├── T01-auth.png ... T15-admin.png
│   └── index.png                      ← 屏幕索引页
├── mockups_html/                      ← 原始 HTML mockup (浏览器可直接打开)
│   └── T01-auth.html ... T15-admin.html
├── DesignHandoff_TokenKnows_MVP.md    ← 详细设计规范 (颜色/字体/组件 token)
└── DesignTasks_TokenKnows_MVP.md      ← 设计任务拆解
```

**PNG 规格**: 全部 device_scale_factor=2 (Retina),宽度 1280–1440px(屏幕),`index.png` 为 1024px。

---

## 2. Figma 文件位置

我已经替你创建好了一个空白 Figma 文件,你可以直接在里面工作:

> **TokenKnows MVP — Mockups (Designer Handoff)**
> https://www.figma.com/design/ut6aOubaZtcPCTl9ocaicQ

(如果你想自建一个新文件也完全可以,这个空文件可以删掉。)

---

## 3. 快速导入步骤 (推荐)

### 方法 A · 一次性拖入所有 PNG (最快,3 分钟)

1. 打开上面的 Figma 文件
2. 在 Finder 里全选 `mockups_png/` 里的 16 张 PNG
3. 直接拖到 Figma 画布
4. Figma 会自动为每张图创建一个 Frame
5. 按 T01 → T15 顺序排列(见下面"建议布局")

### 方法 B · 用 PNG 当底图,在上面重建组件 (高保真,推荐用于设计系统)

适合想沉淀成可复用组件库的情况:

1. 把 PNG 设成 Frame 的 background image,锁定该图层
2. 在 PNG 上覆盖一层 Auto Layout 重建 UI
3. 抽取颜色 / 字体 token 到 Variables (规范见 `DesignHandoff_TokenKnows_MVP.md`)
4. 把按钮、卡片、表单组件做成 Component → Library

---

## 4. 屏幕清单

| # | 屏幕 | 文件名 | 优先级 | 关键交互 |
|---|---|---|---|---|
| T01 | 认证流程 | `T01-auth.png` | P0 | 注册 / 登录 / 邮箱验证 / 找回密码 |
| T02 | 项目创建 + 数据源向导 | `T02-project-setup.png` | P0 | Claude Code / Cursor / VS Code / GitHub 接入 |
| T03 | 工作台首页 | `T03-workbench.png` | P0 | 项目卡 · 实时事件流 · 本周待办 |
| T04 | 事件详情面板 | `T04-event-detail.png` | P0 | 时间轴 / 元数据 / 跳转生成 |
| T05 | 文档列表 | `T05-document-list.png` | P0 | 分类筛选 · 状态徽标 |
| T06 | 文档生成结果页 · 核心 | `T06-document-page.png` | P0 | 章节锚点 · 内联证据 · 重生成 |
| T07 | 证据链抽屉 | `T07-evidence-drawer.png` | P0 | 引用上下文 · 源跳转 |
| T08 | 章节重生成 / 切换模型 | `T08-regenerate-dialog.png` | P0 | 模型选择 · prompt 编辑 |
| T09 | Reviewer 审批视图 | `T09-review.png` | P1 | 评论 / 通过 / 退回 |
| T10 | 脱敏确认面板 | `T10-redaction.png` | P1 | PII 高亮 · 一键脱敏 |
| T11 | 发布对话框 | `T11-publish.png` | P1 | 渠道选择 · 权限确认 |
| T12 | 发布回执 / 版本对比 | `T12-publish-receipt.png` | P1 | Diff 视图 · 链接分享 |
| T13 | 项目设置 | `T13-project-settings.png` | P1 | 成员 / 数据源 / 权限 |
| T14 | LLM 与出域开关 | `T14-llm-egress.png` | P1 | 模型 allowlist · 出域审计 |
| T15 | 实例管理员控制台 | `T15-admin.png` | P1 | 配额 / 审计日志 |

---

## 5. 建议布局 (Figma 画布)

按 5×3 网格排列,T01→T05 第一行,T06→T10 第二行,T11→T15 第三行;
每个 Frame 之间留 200px gap。建议把 `index.png` 放在最左侧作为目录页。

P0 / P1 用 Frame 颜色区分:
- **P0 (核心流程)**: Frame 描边 `#788c5d`
- **P1 (扩展能力)**: Frame 描边 `#bdc9a3`

---

## 6. 设计 Token (品牌色 + 字体)

完整规范在 `DesignHandoff_TokenKnows_MVP.md`,以下是速查:

**核心色板** (Anthropic 风格)
```
背景         #f5f4ed   (warm off-white)
卡片背景     #faf9f5
文字主色     #141413
文字次色     #5d5d57
文字弱化     #85857c
品牌橙       #d97757   (CTA / 强调)
品牌绿       #788c5d   (成功 / P0)
浅绿         #bdc9a3   (描边 / P0 轻量)
背景绿       #eef2e3   (success badge)
警示橙       #b8623f   (warning text)
背景警示橙   #fbeae0   (warning badge)
中性灰       #e8e6dc   (默认 badge)
```

**字体系统**
- 标题: `Lora` (serif) — 字重 400/500/600/700
- 正文: `Poppins` (sans-serif) — 字重 400/500/600/700
- 等宽: ui-monospace / SF Mono

字体在 Figma 里需要确保安装了 Lora + Poppins(Google Fonts)。

---

## 7. 重建优先级建议

如果时间有限,按这个顺序精修:

1. **第一周**: T03 (工作台) + T06 (文档结果页) — 用户停留最久的两个核心屏幕
2. **第二周**: T01 + T02 + T05 — 用户第一次进入产品的链路
3. **第三周**: T04 + T07 + T08 — 文档生成核心交互
4. **第四周**: T09–T15 — 协作和管理类屏幕

---

## 8. 关于素材保真度

PNG 是 Tailwind CSS 浏览器渲染的 2x 截图,**已经是像素级精确**;`mockups_html/` 里可以直接打开看交互态(hover / focus)。

如果需要矢量元素(icon / 图表),原 HTML 里用的是 inline SVG,可以从源码里直接复制 `<svg>` 节点粘到 Figma(粘贴时 Figma 会自动转成可编辑矢量)。

---

## 9. 有问题找谁

- 产品需求 / 优先级: 参见 `PRD_TokenKnows_MVP.md` (项目根目录)
- 设计规范细节: `DesignHandoff_TokenKnows_MVP.md` (本包内)
- 技术约束: `TDD_TokenKnows_MVP.md` (项目根目录)

精修完后回传 Figma file URL 即可,工程会基于 Figma 直接开发。
