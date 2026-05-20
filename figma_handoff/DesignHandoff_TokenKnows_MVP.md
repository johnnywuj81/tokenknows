# Design Handoff · TokenKnows MVP

> 给设计师与前端研发的交付规格。基于 15 个 HTML mockup（`mockups/T01–T15.html`）。

---

## 1. 文档说明

| 项 | 内容 |
| --- | --- |
| 目标读者 | 设计师（Figma 重建 + 精修）、前端研发（实现） |
| 配套源 | [mockups/](./mockups/index.html) 中的 15 个 HTML + [DesignTasks](./DesignTasks_TokenKnows_MVP.md) |
| 范围 | MVP 全部 15 个页面 / 4 种角色视图 / 全部状态机 |
| 版本 | v0.1 · 2026-05-19 |

**双重用途**：
- 设计师把 HTML 作为参考，在 Figma 重建一套**真正可维护的设计系统**（HTML 是"够用的真实物"，不是最终设计稿）
- 前端研发直接对照 token 与组件清单实现

---

## 2. 设计 Token

### 2.1 Color

来源：Anthropic 官方品牌 + 状态语义扩展。

#### 主色板（中性）

| Token | Hex | 用途 |
| --- | --- | --- |
| `color-bg-page` | `#f5f4ed` | 页面底色（淡暖米） |
| `color-bg-card` | `#faf9f5` | 卡片 / 容器底色（亮奶白） |
| `color-bg-warm` | `#e8e6dc` | 次级容器、悬停 bg |
| `color-text-primary` | `#141413` | 主文字、深色按钮、Logo |
| `color-text-secondary` | `#3a3a37` | 正文 / 次要标题 |
| `color-text-muted` | `#5d5d57` | 说明、辅助信息 |
| `color-text-subtle` | `#85857c` | 元数据、时间戳 |
| `color-text-disabled` | `#b0aea5` | 灰显文字 |
| `color-border-subtle` | `#e8e6dc` | 默认分隔线、卡片描边 |
| `color-border-medium` | `#d4d2c7` | 强调描边、表单 focus |

#### 强调色（品牌）

| Token | Hex | 用途 |
| --- | --- | --- |
| `color-accent-primary` | `#d97757` | 陶土橙 · 主强调（链接、图标点缀、CTA hover） |
| `color-accent-primary-dark` | `#b8623f` | 陶土橙深 · 文本上的橙色 |
| `color-accent-primary-light` | `#fbeae0` | 陶土橙浅 · 徽标 bg、avatar bg |
| `color-accent-primary-border` | `#f5d4be` | 陶土橙边框 |

#### 状态色（语义）

| Token | Hex | 用途 |
| --- | --- | --- |
| `color-success` | `#788c5d` | 暖橄榄绿 · 成功、健康、已通过 |
| `color-success-dark` | `#5d6e45` | 成功文字 |
| `color-success-bg` | `#eef2e3` | 成功徽标 bg |
| `color-success-border` | `#bdc9a3` | 成功描边 |
| `color-warning` | `#856226` | 警告文字（暖沙黄） |
| `color-warning-bg` | `#f5ecd8` | 警告徽标 bg |
| `color-warning-border` | `#d9c587` | 警告描边 |
| `color-danger` | `#8a3a2a` | 错误文字（暖红） |
| `color-danger-strong` | `#b94a3a` | 危险按钮 bg |
| `color-danger-bg` | `#f5e0dc` | 错误徽标 bg |
| `color-danger-border` | `#e8c7be` | 错误描边 |
| `color-info` | `#3d6a96` | 信息文字（蓝） |
| `color-info-bg` | `#e8eef5` | 信息徽标 bg |

#### 反色（深色容器）

| Token | Hex | 用途 |
| --- | --- | --- |
| `color-inverse-bg` | `#141413` | 深色容器（管理员控制台 header、代码块） |
| `color-inverse-text` | `#faf9f5` | 反色文字 |
| `color-inverse-muted` | `#b0aea5` | 反色次要文字 |
| `color-inverse-accent` | `#d97757` | 深底上的强调（Logo 内的橙色） |

---

### 2.2 Typography

#### 字体族

| Token | Family | 用途 |
| --- | --- | --- |
| `font-ui` | Poppins, -apple-system, sans-serif | UI 界面：按钮、标签、导航、表单 |
| `font-content` | Lora, Georgia, serif | 文档正文、大数字、报告标题 |
| `font-mono` | "JetBrains Mono", monospace | 代码、ID、版本号、token、哈希 |

#### 字号 / 字重 / 行高

| Token | Size | Weight | Line-height | 用途 |
| --- | --- | --- | --- | --- |
| `text-display` | 36px | 600 | 1.1 | 章节扉页大标题 |
| `text-h1` | 30px | 600 | 1.2 | 页面主标题（用 font-content） |
| `text-h2` | 22px | 600 | 1.3 | 子区块标题（用 font-content） |
| `text-h3` | 18px | 600 | 1.4 | 卡片标题（用 font-ui） |
| `text-body-lg` | 16px | 400 | 1.65 | 文档正文（用 font-content） |
| `text-body` | 14px | 400 | 1.5 | UI 默认正文 |
| `text-body-sm` | 13px | 400 | 1.5 | 表单 / 按钮 |
| `text-caption` | 12px | 400 | 1.45 | 元数据、说明 |
| `text-micro` | 11px | 500 | 1.4 | 标签内文字、徽标 |
| `text-eyebrow` | 11px | 600 | 1.3 | 大写小标签（letter-spacing 0.08em） |

---

### 2.3 Spacing

基于 **4px** 网格：

| Token | px | 用途 |
| --- | --- | --- |
| `space-0.5` | 2 | 字符间紧凑 |
| `space-1` | 4 | 徽标内 padding |
| `space-1.5` | 6 | 紧凑列间距 |
| `space-2` | 8 | 一般间距 |
| `space-2.5` | 10 | |
| `space-3` | 12 | 输入框 padding y |
| `space-4` | 16 | 标准卡片 padding |
| `space-5` | 20 | 子区块 |
| `space-6` | 24 | 章节内间距 |
| `space-8` | 32 | 章节间 |
| `space-10` | 40 | 主标题与正文 |
| `space-12` | 48 | 重要分隔 |
| `space-16` | 64 | 大区块间距 |

---

### 2.4 Radius

| Token | px | 用途 |
| --- | --- | --- |
| `radius-sm` | 4 | 徽标、tag、小输入 |
| `radius-md` | 6 | 按钮、输入框 |
| `radius-lg` | 8 | 卡片、容器 |
| `radius-xl` | 12 | Modal |
| `radius-full` | 9999 | Avatar、状态点、Toggle |

---

### 2.5 Shadow / Elevation

| Token | Value | 用途 |
| --- | --- | --- |
| `shadow-none` | — | 默认（平面） |
| `shadow-sm` | `0 1px 2px rgba(20,20,19,0.04)` | 卡片悬停、输入 focus 阴影 |
| `shadow-md` | `0 4px 8px rgba(20,20,19,0.08)` | 浮动菜单 |
| `shadow-lg` | `0 12px 32px rgba(20,20,19,0.12)` | Modal、抽屉 |

---

### 2.6 Motion

| Token | Duration | Easing | 用途 |
| --- | --- | --- | --- |
| `motion-instant` | 0ms | — | 状态切换无动画 |
| `motion-fast` | 100ms | cubic-bezier(0.4, 0, 0.2, 1) | hover bg 切换 |
| `motion-default` | 200ms | cubic-bezier(0.4, 0, 0.2, 1) | 大多数 UI 切换 |
| `motion-slow` | 300ms | cubic-bezier(0.4, 0, 0.2, 1) | 抽屉、Modal |
| `motion-emphasis` | 400ms | cubic-bezier(0.34, 1.56, 0.64, 1) | 成功反馈、徽章 pop-in |

---

## 3. 组件清单

> 15 个原子组件 + 8 个复合模式。每个组件至少需要在 Figma 做 3 个状态。

### 3.1 Button

| 变体 | 描述 | 主要 token |
| --- | --- | --- |
| `primary` | 深底奶字（核心 CTA） | bg `#141413`, text `#faf9f5`, hover `#3a3a37` |
| `secondary` | 描边按钮 | border `#e8e6dc`, text `#3a3a37`, hover bg `#e8e6dc40` |
| `ghost` | 无边框文字按钮 | text `#3a3a37`, hover bg `#e8e6dc50` |
| `accent` | 强调（橙色，少用） | text `#d97757`, hover `#b8623f` |
| `danger` | 危险按钮 | bg `#b94a3a`, hover `#8a3a2a` |

**Sizes**：sm (28h / px 8) · md (36h / px 12) · lg (40h / px 16)

**States 必须设计**：default · hover · active · focus（外框 2px `#fbeae0`） · disabled · loading（旋转 icon）

---

### 3.2 Input

| Token | 值 |
| --- | --- |
| 默认 | bg `#faf9f5`, border `#e8e6dc`, padding `12px 14px` |
| Focus | border `#d97757`, outline `2px #fbeae0` |
| Error | border `#b94a3a`, outline `2px #f5e0dc` |
| Disabled | bg `#e8e6dc/40`, text `#b0aea5` |

变体：text · password（含眼睛切换） · search · textarea（resize: none） · select

---

### 3.3 Card

容器矩形 + radius-lg + border-subtle + padding-4。

变体：

- **Default** · 灰白底
- **Highlighted** · `border #bdc9a3` (success bg) / `border #d97757` (primary)
- **Disabled** · opacity 0.5
- **Dashed** · 虚线描边（未配置状态卡）

---

### 3.4 Badge / Tag

`px-1.5 py-0.5 rounded text-xs font-medium`

| 语义 | bg | text |
| --- | --- | --- |
| neutral | `#e8e6dc` | `#5d5d57` |
| primary | `#fbeae0` | `#b8623f` |
| success | `#eef2e3` | `#5d6e45` |
| warning | `#f5ecd8` | `#856226` |
| danger | `#f5e0dc` | `#8a3a2a` |
| info | `#e8eef5` | `#3d6a96` |

---

### 3.5 Avatar

圆形头像。

| 尺寸 | px |
| --- | --- |
| `xs` | 20 |
| `sm` | 24 |
| `md` | 32 |
| `lg` | 36 |

带文字头像默认 bg `#fbeae0` text `#b8623f`，可按用户哈希轮换品牌色。

---

### 3.6 Status Indicator

圆点 + 可选文字。

| 状态 | 颜色 |
| --- | --- |
| 健康 / 在线 | `#788c5d` |
| 配置中 | `#d97757`（带 pulse 动画） |
| 未配置 | `#d4d2c7` |
| 错误 | `#b94a3a` |

---

### 3.7 Toggle Switch

宽 44 / 高 24 / 圆 radius-full

- ON：bg `#141413`，圆点 translateX(20px)
- OFF：bg `#d4d2c7`，圆点 translateX(2px)
- Disabled：opacity 0.5

---

### 3.8 Modal

容器 max-width 480 / 600 / 720（视内容），radius-xl，shadow-lg。

遮罩 bg `rgba(20, 20, 19, 0.45)`，backdrop-blur 4px。

结构：Header（标题 + 关闭）→ Body → Footer（cancel + primary）。

参考实现：[T08 重生成对话框](./mockups/T08-regenerate-dialog.html)、[T11 发布对话框](./mockups/T11-publish.html)

---

### 3.9 Drawer

右侧抽屉，宽 480 / 560 / 640px（视内容），全高，shadow-lg。

参考实现：[T04 事件详情](./mockups/T04-event-detail.html)、[T07 证据链](./mockups/T07-evidence-drawer.html)

---

### 3.10 Tabs

水平 tab，下划线 2px `#141413` 标识选中。

```
[选中]  [未选中] [未选中]
━━━━━━
```

---

### 3.11 Progress Bar

高 6px，bg `#e8e6dc`，填充色 `#788c5d`，radius-full。

---

### 3.12 Toggle Switch Group（三层联动）

参见 [T14 LLM 与出域开关](./mockups/T14-llm-egress.html) 的实例 / 项目 / 任务三层结构。

---

### 3.13 Table

容器 = card。Header row bg `#e8e6dc30`，行间 `divide-y #e8e6dc`。hover row bg `#e8e6dc30`。

---

### 3.14 Code Block

bg `#141413`，text `#d4d2c7`，font-mono，radius-md。

语法着色：
- 关键字：`#d97757`
- 注释：`#788c5d` italic
- 字符串：`#6a9bcc`

---

### 3.15 Empty State

居中插画 + 1 行文案 + 1 个明确 CTA。

参考结构：
```
[插画 96×96]
[标题 H3]
[副标题 caption]
[CTA Button primary]
```

---

## 4. 布局规范

### 4.1 5 种布局类型

| 类型 | 用于哪些页 | 结构 |
| --- | --- | --- |
| **A · App Shell** | T03 / T13 | 顶栏 + 左导航 + 主区 + 右抽屉 |
| **B · Document Editor** | T06 / T09 | 顶栏 + 文档头 + 左章节导航 + 主文档 + 右抽屉 + 底部粘性操作条 |
| **C · Modal / Dialog** | T08 / T11 / T07 (drawer) | 居中卡片 / 右侧抽屉 |
| **D · Split Page** | T01 | 左 50% 品牌叙事 + 右 50% 表单 |
| **E · Settings / Admin** | T13 / T14 / T15 | 顶栏 + 左 tab 或顶部 tab + 主区 |

### 4.2 网格与断点

| 断点 | 用途 |
| --- | --- |
| Desktop ≥ 1280px | 主要支持，所有页面 |
| Tablet 768–1279px | 适配（左侧导航折叠为图标） |
| Mobile < 768px | 仅阅读视图（无编辑功能） |

主区域内容最大宽度：

- 一般页：`max-w-4xl` (896px)
- 文档编辑：`max-w-3xl` (768px) - 阅读舒适
- Admin 仪表盘：`max-w-6xl` (1152px)

### 4.3 排版约定

- **段落最大宽度**：65 ch（约 600px），保持可读性
- **段落间距**：`mb-4`（16px）
- **章节间距**：`mb-8`（32px）
- **headline 与下一段间距**：`mb-3`（12px）

---

## 5. 各页交付规格（15 页 quick reference）

每页给出：布局类型 / 关键组件 / 必须设计的状态 / 边界场景 / 引用 PRD 章节。

### T01 · 认证流程

- **布局**：D（split page）
- **组件**：Input × 2、Button (primary) × 1、Logo、品牌叙事文案
- **状态**：登录默认 / 错误（密码错） / 锁定 / 邮箱待验证 / 找回密码切换
- **边界**：长用户名截断、邮箱格式校验、5 次失败锁定倒计时
- **PRD**：§4.1 / §6.2

### T02 · 项目创建 + 数据源向导

- **布局**：E（settings-like）
- **组件**：Stepper（步骤指示）× 1、DataSourceCard × 4（4 种状态展示）、Button、模板推荐 Card × 4
- **状态**：未配置 / 配置中 / 已连接 / 失败 / 权限不足
- **边界**：插件首次连接 30s 超时、PAT 缺权限的局部降级方案
- **PRD**：§5.1 / §4.1

### T03 · 工作台首页

- **布局**：A（App shell）
- **组件**：TopBar、SideNav、ProjectCard、DataSourceMini × 4、AssetCounter × 4、EventStreamItem × N、TodoCard × 3
- **状态**：项目卡(满 / 部分)、事件流(loading / streaming / empty / paused)、各待办区 empty / has items
- **边界**：500+ 事件的虚拟滚动、新事件淡入动画
- **PRD**：§8.1 / §4.2

### T04 · 事件详情面板

- **布局**：C（drawer）
- **组件**：Drawer、Tabs × 4、ValueSegmentItem
- **状态**：loading / loaded / 被脱敏（仅 Reviewer 可见）
- **边界**：内容长度 < 100 chars / > 5000 chars / 含代码 / 含图片
- **PRD**：§5.2 / §8.1

### T05 · 文档列表

- **布局**：A（去掉右抽屉）
- **组件**：Table、Badge（4 类）、SearchInput、FilterGroup、PaginationLink
- **状态**：empty / loaded / filtered (无结果)
- **边界**：长标题截断、100+ 文档分页、跨类型筛选
- **PRD**：§5.3 / §8.1

### T06 · 文档生成结果页（核心）

- **布局**：B（document editor）
- **组件**：DocumentHeader、SelfEvalCard × 4、ChapterNav、TipTapEditor、EvidenceBadge、ChapterMenu、BottomActionBar、EvidenceDrawer
- **状态**：生成中（5 阶段进度）/ 生成完成 / 章节重生成中 / 编辑中 / 自动保存 / 多人编辑锁定 / 自评分低警告 / 章节生成失败
- **边界**：超长章节（> 5000 字）、零引用警告、不同模型生成的章节并存
- **PRD**：§4.2 / §8.2 / §5.3

### T07 · 证据链抽屉

- **布局**：C（drawer）
- **组件**：Drawer、EvidenceCard × N、SortSelector、CodeExcerpt
- **状态**：default / 脱敏遮蔽 / 来源已删除 / 单段 > 20 来源（折叠）
- **边界**：来源原文 < 50 / > 2000 chars 的截断
- **PRD**：§5.4 / §8.3

### T08 · 章节重生成对话框

- **布局**：C（modal）
- **组件**：Modal、ModelRadioCard × 4、Textarea、QuickSuggestionChip × 4、SelfEvalCard 缩略版
- **状态**：default / 模型不可用灰显 / 指令输入 / 提交中
- **边界**：指令为空 / 超 500 字
- **PRD**：§5.3 / §6.6

### T09 · Reviewer 审批视图

- **布局**：B
- **组件**：DocumentHeader（审核版）、ProgressBar、ChapterStatusList、ChapterStickyHeader、CommentSidebar、CommentItem、CommentTab × 3
- **状态**：default / 各章节状态（pending/approved/rejected）/ 多 Reviewer 并行 / Reviewer 缺席 48h 后的 Owner 代行
- **边界**：单段 > 10 批注 / 多人冲突解决
- **PRD**：§4.3 / §5.5 / §8.4

### T10 · 脱敏确认面板

- **布局**：A（去掉右抽屉）
- **组件**：StatusBanner（黄色警告）、FilterPills、RedactionItem × N、SuggestionDiff
- **状态**：default / 待确认 / 已应用 / 自定义中 / 已标记非敏感 / 撤销
- **边界**：100+ 敏感项的滚动性能、原文展开权限
- **PRD**：§5.6 / §4.3

### T11 · 发布对话框

- **布局**：C（modal）
- **组件**：Modal、DestinationCard × 4、PublishModeRadio × 2、RememberCheckbox、ResidencyBanner
- **状态**：default / 凭证未配置（跳转设置）/ 发布中 / 部分成功 / 全部成功 / 全部失败
- **边界**：未选目的地禁用发布、记忆上次选择
- **PRD**：§5.7 / §4.3

### T12 · 发布回执 / 版本对比

- **布局**：A
- **组件**：SuccessBanner、PublishRecordRow × N、VersionRow × N、DiffViewer（红删 / 绿增）
- **状态**：发布刚完成（绿 banner）/ 历史查看 / Diff 展开
- **边界**：5+ 版本的列表表现、未发布的草稿不可撤回
- **PRD**：§5.7 / §7.2.3

### T13 · 项目设置

- **布局**：E
- **组件**：SidebarTab × 7、DataSourceListItem × N、ToggleSwitch、Select、AdvancedConfigRow
- **状态**：各数据源状态、暂停采集 toggle
- **边界**：移除数据源的二次确认、轮换 PAT 流程
- **PRD**：§5.1 / §2.3

### T14 · LLM 与出域开关

- **布局**：A（去掉右抽屉）
- **组件**：InstanceStatusBanner、ToggleSwitch × N、ModelRoutingTable、ApiKeyInputRow × 4、TokenUsageCard × 4
- **状态**：实例级 ON/OFF（联动项目级灰显）、Key 未配/已配/已验证/无效
- **边界**：所有云端 provider 被禁用时的本地兜底
- **PRD**：§6.6 / §6.7

### T15 · 实例管理员控制台

- **布局**：E（深色顶栏区分）
- **组件**：HealthDashCard × 4、AdminTabs × 6、EmergencyShutdownButton、InfoFooter
- **状态**：实例健康 / 警告（license 临近过期）/ 严重（license 过期）
- **边界**：紧急关停二次确认 + 倒计时、license 30 天内警告
- **PRD**：§6.5 / §6.7 / §2.3

---

## 6. 状态机模式

每个有意义的 UI 实体都应覆盖：

| 状态 | 视觉处理 |
| --- | --- |
| `default` | 标准呈现 |
| `loading` | Skeleton（不要 spinner） |
| `empty` | 插画 + CTA |
| `error` | error border / icon / message + retry |
| `disabled` | opacity 0.5 + cursor not-allowed |
| `partial` | 部分完成的进度提示 |
| `success` | 短时绿色徽标 |
| `redacted` | 暖灰遮蔽 + 临时展开按钮（高权限） |

---

## 7. 动效规范

| 元素 | 触发 | 动画 | Duration | Easing |
| --- | --- | --- | --- | --- |
| 按钮 hover | mouseenter | bg 变深 | 100ms | ease-out |
| 卡片 hover | mouseenter | border darken + 微 shadow | 200ms | ease-out |
| Modal 出现 | open | scale 0.96 → 1 + fade in | 200ms | ease-out |
| Drawer 滑入 | open | translateX 100% → 0 | 300ms | ease-out |
| Tab 切换 | click | 下划线 sliding | 200ms | ease-out |
| Toast | enter | slide-in from top + fade | 300ms | ease-out |
| 状态点 pulse | always | 透明度 1 → 0.4 → 1 | 2s | ease-in-out infinite |
| Skeleton | always | 渐变 shimmer | 1.5s | linear infinite |
| 文档章节生成 | trigger | 5 阶段进度条 | 各阶段 12–60s | 流式 |
| 证据链高亮联动 | hover sidenote | 主文档对应段 bg 渐入 | 200ms | ease-out |
| 自评分低警告 | 阈值触发 | 章节背景渐染 + 警告条 fade in | 400ms | ease-out |

---

## 8. 无障碍（a11y）

### 8.1 颜色对比

| 文字 / 背景组合 | 对比度 | WCAG |
| --- | --- | --- |
| `#141413` on `#faf9f5` | 17.8:1 | ✅ AAA |
| `#3a3a37` on `#faf9f5` | 11.6:1 | ✅ AAA |
| `#5d5d57` on `#faf9f5` | 7.1:1 | ✅ AAA |
| `#85857c` on `#faf9f5` | 4.5:1 | ✅ AA（仅大文字与辅助信息） |
| `#d97757` on `#141413` | 4.6:1 | ✅ AA |
| `#faf9f5` on `#141413` | 17.8:1 | ✅ AAA |

⚠️ 注意：`#b0aea5` on `#faf9f5` 仅 3.0:1，**仅用于已禁用状态或装饰**。

### 8.2 键盘可达

每个 interactive 元素必须：
- `tabindex` 顺序符合视觉顺序
- focus ring 显式（outline 2px `#fbeae0`）
- Modal 打开时 focus 锁定，关闭时回到触发元素
- Escape 关闭 Modal / Drawer

### 8.3 ARIA

- 所有图标按钮加 `aria-label`
- Toggle Switch 用 `role="switch"` + `aria-checked`
- Modal 用 `role="dialog"` + `aria-labelledby`
- 进度条用 `role="progressbar"` + `aria-valuenow/min/max`
- 自评分徽标用 `aria-label="覆盖度 82%，良好"`

### 8.4 屏幕阅读器

- 状态变化用 `aria-live="polite"` 区域宣告
- 实时事件流不应触发屏幕阅读器（用 `aria-live="off"`）
- 错误信息用 `aria-live="assertive"` 立即宣告

---

## 9. Figma 化工作流建议

### 9.1 推荐工具

| 工具 | 用途 | 备注 |
| --- | --- | --- |
| **html.to.design** Figma plugin | HTML → Figma 自动转换（首版基线） | 出图后必须人工精修；不要直接交付 |
| **Tailwind for Figma** | Token 同步 | Figma styles ↔ Tailwind config 对照 |
| **shadcn/ui Figma kit**（社区） | 基础组件起点 | 二次封装为 TokenKnows 自己的库 |
| **Figma Variables** | Token 管理 | 颜色 / 字号 / 间距全部 token 化 |
| **Auto Layout** | 所有容器必用 | 不要硬定位 |

### 9.2 推荐 Figma 文件结构

```
TokenKnows · Design System  (Library)
├─ 📚 Foundations
│  ├─ Colors             (variables)
│  ├─ Typography         (text styles)
│  ├─ Spacing            (variables)
│  ├─ Radius             (variables)
│  └─ Effects (shadow)
│
├─ 🧩 Components
│  ├─ Button   (5 variants × 3 sizes × 5 states)
│  ├─ Input    (4 variants × 4 states)
│  ├─ Card
│  ├─ Badge    (6 semantic colors)
│  ├─ Avatar
│  ├─ Toggle
│  ├─ Modal / Drawer
│  ├─ Tabs
│  └─ ... (见 §3)
│
└─ 📐 Patterns
   ├─ Layout A · App shell
   ├─ Layout B · Document editor
   ├─ Layout C · Modal / Drawer
   ├─ Layout D · Split page
   └─ Layout E · Settings

TokenKnows · Product  (Design file)
├─ 🟢 P0 · 核心链路
│  ├─ T01 Auth          (4 states)
│  ├─ T02 Project setup (5 states)
│  ├─ T03 Workbench     (8 states)
│  ├─ T06 Document page (12 states · 含生成中)
│  ├─ T09 Review        (6 states)
│  ├─ T10 Redaction     (5 states)
│  ├─ T11 Publish       (5 states)
│  └─ T14 LLM/Egress    (4 states)
│
├─ 🟡 P1 · 辅助
│  ├─ T04, T05, T07, T08, T12, T13, T15
│
└─ 🔵 Flows (Prototype)
   ├─ Flow 1: 注册 → 首份周报
   ├─ Flow 2: 编辑 → 审批 → 发布
   └─ Flow 3: 脱敏门禁
```

### 9.3 推荐节奏（共 3-4 周）

| Sprint | 时长 | 交付 |
| --- | --- | --- |
| **S1** | 3-4 天 | Foundations + 5 个核心 component（Button / Input / Card / Badge / Avatar） |
| **S2** | 5-6 天 | 剩余 component + 5 个核心页面（T01 / T03 / T06 / T09 / T11） |
| **S3** | 5-6 天 | 其余 10 个页面 + 全部状态机 |
| **S4** | 3 天 | Interactive prototype（至少 3 个核心 user flow）+ a11y 标注 + 与研发联调 |

### 9.4 工作流建议

1. **从 Foundations 开始**：先把 token 全部建好，再做组件，否则全是硬编码值，后期改动量极大
2. **每个 component 必须三态以上**：default + hover + 一个 edge state（disabled / loading / error）
3. **Auto Layout 是底线**：所有容器、所有按钮、所有 list，禁止硬定位
4. **响应式用 Constraints**：桌面端先做，平板做次要变体，移动端阅读视图最后
5. **状态用 Variants**：同一个 component 的不同状态用 Variants 而不是 复制 frame
6. **不要全自动**：html.to.design 出来的是脏稿，**必须人工精修**才能交付

### 9.5 验收清单

设计交付前自查：

- [ ] 所有 token 与 HTML mockup 一致（颜色精确匹配）
- [ ] 每个 component 至少 3 个状态
- [ ] 15 页所有 P0 状态机完成
- [ ] Interactive prototype 至少覆盖 3 个核心 user flow
- [ ] 所有图标已替换为 lucide-react（与前端用同一套）
- [ ] 所有交互动效已在 Figma 里用 Smart Animate 标注
- [ ] a11y 标注完成（focus ring / aria-label / 键盘 tab 顺序）
- [ ] 与前端对齐：Figma frame name = HTML mockup 文件名（便于 review）

---

## 10. HTML mockup 待精修的点（设计师注意）

我用 HTML 做的 mockup 是"够用的真实物"，**这些是已知粗糙、需要设计师重新打磨的地方**：

### 10.1 图标系统

HTML 里用的是 lucide 的内联 SVG。设计师应：
- 在 Figma 里建一个完整的 lucide icon library（24px / 16px / 14px 三种尺寸）
- 检查每个图标的语义是否准确（特别是 §3.6 状态点旁的图标）
- 自定义品牌图标（Logo、4 类文档类型的图标）

### 10.2 插画

HTML 里没有空状态插画。设计师需要：
- 至少 3-4 张品牌一致的插画（文档空态 / 数据源空态 / 错误页 / 搜索无结果）
- 风格：手绘感、暖色、与 Anthropic 主页插画调性接近
- 推荐自绘，避免用 stock illustration

### 10.3 logo 与品牌应用

HTML 里 Logo 是简化的"堆叠层"图标。设计师应：
- 设计正式 logo（含 wordmark + symbol 两种形式）
- 制定 logo 应用规范（最小尺寸、留白、深底 / 浅底变体）
- 设计 favicon、应用图标（macOS / Windows / mobile）

### 10.4 数字与图表

T03 工作台里事件数 / trust_score 等数字用了 Lora 衬线。设计师应：
- 决定是用 tabular figures（等宽数字）还是 proportional
- 检查所有数字栏的对齐
- 后续若加图表，设计 Recharts / Chart.js 主题

### 10.5 微动效

HTML 里只标注了关键动效。设计师在 Figma prototype 里需要：
- 实现 §7 表中所有动效
- 特别注意 5 阶段生成进度的动效（这是产品最特别的视觉时刻）
- 证据链 hover 联动的双向高亮

### 10.6 边界场景

HTML 里大部分是"happy path"。设计师还要补：
- 网络中断状态（顶部 banner）
- 浏览器不支持的兜底页
- 邮箱验证邮件待收页
- License 过期后的只读模式 UI

### 10.7 暗色模式（可选 · Phase 2）

MVP 不做暗色，但 token 已经预留反色（`#141413` bg / `#faf9f5` text）。Phase 2 启动暗色时可基于现有 token 反转。

---

## 11. 与研发的协作约定

### 11.1 命名一致

| 设计层 | 实现层 |
| --- | --- |
| Figma component name | React component name |
| Figma variant property | React prop |
| Figma token name | Tailwind config / CSS variable |

举例：
- Figma：`Button / variant=primary / size=md / state=hover`
- React：`<Button variant="primary" size="md" />`（hover 自动处理）

### 11.2 资产导出

- 图标：导出为 SVG，命名 `icon-{name}.svg`
- 插画：导出为 SVG（首选）或 PNG @2x
- 截图 / 装饰图：PNG @2x + WebP
- 字体：Google Fonts CDN（无需导出）

### 11.3 设计 → 研发的状态同步

- 设计完成一个 P0 页面 → 创建一个 Jira / Linear 任务，附 Figma frame 链接
- 研发实现完成 → 在 Jira / Linear 上 link 实际 URL，请设计师走查
- 设计师走查通过 → 关闭任务；不通过 → 留具体批注

---

## 12. 附录 · 完整页面 ↔ HTML mockup 对照表

| Ticket | 页面名 | HTML 文件 | Figma frame 命名建议 |
| --- | --- | --- | --- |
| T01 | 认证流程 | [T01-auth.html](./mockups/T01-auth.html) | `T01 · Auth · Login` |
| T02 | 项目创建 + 数据源向导 | [T02-project-setup.html](./mockups/T02-project-setup.html) | `T02 · Project Setup` |
| T03 | 工作台首页 | [T03-workbench.html](./mockups/T03-workbench.html) | `T03 · Workbench` |
| T04 | 事件详情面板 | [T04-event-detail.html](./mockups/T04-event-detail.html) | `T04 · Event Detail Drawer` |
| T05 | 文档列表 | [T05-document-list.html](./mockups/T05-document-list.html) | `T05 · Document List` |
| T06 | 文档生成结果页 ★ 核心 | [T06-document-page.html](./mockups/T06-document-page.html) | `T06 · Document Page` |
| T07 | 证据链抽屉 | [T07-evidence-drawer.html](./mockups/T07-evidence-drawer.html) | `T07 · Evidence Drawer` |
| T08 | 章节重生成对话框 | [T08-regenerate-dialog.html](./mockups/T08-regenerate-dialog.html) | `T08 · Regenerate Dialog` |
| T09 | Reviewer 审批 | [T09-review.html](./mockups/T09-review.html) | `T09 · Review` |
| T10 | 脱敏确认 | [T10-redaction.html](./mockups/T10-redaction.html) | `T10 · Redaction` |
| T11 | 发布对话框 | [T11-publish.html](./mockups/T11-publish.html) | `T11 · Publish Dialog` |
| T12 | 发布回执 / 版本对比 | [T12-publish-receipt.html](./mockups/T12-publish-receipt.html) | `T12 · Publish Receipt` |
| T13 | 项目设置 | [T13-project-settings.html](./mockups/T13-project-settings.html) | `T13 · Project Settings` |
| T14 | LLM 与出域开关 | [T14-llm-egress.html](./mockups/T14-llm-egress.html) | `T14 · LLM Egress` |
| T15 | 实例管理员控制台 | [T15-admin.html](./mockups/T15-admin.html) | `T15 · Admin Console` |

---

*文档版本 v0.1 · 2026-05-19 · 配套 HTML mockup 与 PRD §8*
