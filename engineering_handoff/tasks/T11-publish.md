# T11 · 发布对话框

## 1. 目标
选择发布渠道(站内 / 公开链接 / 导出文件)、确认权限,触发发布。
PRD: §5.7 模块 G · 导出与发布

## 2. 路由
不是独立路由,是从 T06/T09/T10 触发的 Dialog。可选 deeplink `?publish=open`。

## 3. 视觉参考
`docs/mockups/T11-publish.html` · 中等尺寸 Dialog (640px)

## 4. API

| 操作 | 端点 |
|---|---|
| 发布 | `POST /api/v1/assets/{asset_id}/publish` body `{destinations[], publish_mode}` |
| 导出文件 | `POST /api/v1/assets/{asset_id}/export` body `{format: md|docx|pdf}` → 返回下载 URL |

## 5. 组件分解

```
src/features/publish/
├── PublishDialog.tsx
├── components/
│   ├── DestinationSelector.tsx     ← 渠道选择(多选)
│   ├── VisibilityPicker.tsx        ← Private / Team / Public
│   ├── ExpiryPicker.tsx            ← 链接有效期(可选)
│   └── ConfirmChecklist.tsx        ← 发布前确认清单
└── hooks/
    └── usePublishAsset.ts
```

shadcn 用: `Dialog` `Checkbox` `RadioGroup` `Select` `Button` `Card` `Tooltip`

## 6. 状态管理

- Dialog 表单 state: useState
- 提交后 → mutation → 跳 T12 发布回执

## 7. 必备状态

- [ ] Loading: 发布中 spinner
- [ ] Empty: 不适用
- [ ] Error: dialog 内行级 + toast
- [ ] Success: 关闭 dialog + 跳 T12

## 8. 验收

- [ ] 三种渠道: 站内文档库 / 公开链接 / 导出文件(各自有 sub-options)
- [ ] 公开链接需选择 visibility (Private/Team/Public) + 可选过期日期
- [ ] 导出文件支持 md / docx / pdf,各自下载
- [ ] 确认清单包含: "已完成脱敏" / "审批已通过" / "了解公开后不可撤销 PII" 等
- [ ] 提交按钮在确认清单未全勾时 disabled
- [ ] 文档状态非"已通过"时,显示"需先审批通过"+ 禁用提交
- [ ] 发布成功后跳 T12 发布回执页

## 9. 已知陷阱

- 公开链接生成的 URL 是 unguessable token,前端不要尝试预测
- 导出 pdf 是同步阻塞 API(后端渲染慢),要长 timeout + 加载状态
- "导出文件"和"在线发布"可以同时选,后端独立处理
- 重新发布会生成新版本,旧版本可在 T12 看到 diff

## 10. Claude Code 指令
导出按钮是异步下载,用 fetch + blob + a.click() 触发浏览器下载,不要让 axios 兜流。
