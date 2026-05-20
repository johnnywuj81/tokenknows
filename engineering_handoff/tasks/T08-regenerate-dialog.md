# T08 · 章节重生成 / 切换模型

## 1. 目标
让用户对单个章节重生成,可调整 prompt 指令、切换 LLM 模型。
PRD: §5.3 模块 C · 文档自动生成

## 2. 路由
不是独立路由,是 T06 文档页 ChapterFooter 里"重生成"按钮触发的 Dialog(模态对话框)。

## 3. 视觉参考
`docs/mockups/T08-regenerate-dialog.html`

## 4. API

| 操作 | 端点 |
|---|---|
| 重生成章节 | `POST /api/v1/assets/{asset_id}/chapters/{chapter_id}/regenerate` body `{instruction, model}` |
| 获取可用模型 | `GET /api/v1/projects/{id}/llm/models`(返回 allowlist) |

## 5. 组件分解

```
src/features/generation/
├── RegenerateDialog.tsx
├── components/
│   ├── ModelSelector.tsx          ← Radio 卡片样式,显示 capability/cost
│   ├── InstructionEditor.tsx      ← Textarea + prompt 模板下拉
│   └── ContextPreview.tsx         ← 展示会带入的上下文(只读)
└── hooks/
    └── useRegenerateChapter.ts
```

shadcn 用: `Dialog` `RadioGroup` `Textarea` `Button` `Select` `Card` `Badge`

## 6. 状态管理

- Dialog open/close: 父组件 prop
- 表单本地 state: useState
- 提交后 → invalidate 文档章节 query → 关闭 dialog

## 7. 必备状态

- [ ] Loading: 提交按钮 spinner
- [ ] Empty: 无可用模型 → 提示去 T14 配置
- [ ] Error: dialog 内行级红字
- [ ] Success: 关闭 dialog + 章节进入"重生成中"状态

## 8. 验收

- [ ] 默认模型选项卡显示 3 个: GPT-4o / Claude-3.5-Sonnet / 本地(allowlist 内)
- [ ] 模型卡显示: 名称 / 速度估计 / token 估算 / 是否私有
- [ ] Instruction 文本框预填当前章节生成指令,可改
- [ ] "应用模板"下拉:更口语化 / 更技术 / 更短 / 更长
- [ ] 上下文预览展示这次会带入哪些事件(可折叠)
- [ ] 提交后立即关 dialog,章节卡进入"生成中"状态(由 T06 控制)
- [ ] Esc / 点遮罩可关 dialog;有未保存修改时二次确认
- [ ] 提交按钮 disabled 直到 instruction 不为空

## 9. 已知陷阱

- 模型 allowlist 由 T14 配置,前端只列出后端返回的可用模型
- "本地模型"如果未配置,显示但 disabled + tooltip 提示
- 重生成会产生新版本,旧版本不丢(可在 T12 看到 diff)
- prompt 模板内容硬编码在前端,不要让后端管

## 10. Claude Code 指令
单文件简单组件,跟随 T06 一起做。
