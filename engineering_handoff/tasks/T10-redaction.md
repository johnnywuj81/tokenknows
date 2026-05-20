# T10 · 脱敏确认面板

## 1. 目标
发布前自动扫描 PII / 密钥 / 内部敏感词,让用户逐条确认是否脱敏。
PRD: §5.6 模块 F · 脱敏与合规

## 2. 路由
- 路径: `/projects/:id/documents/:docId/redaction`
- 入口: T06 文档页 "提交审批" 前,或 T11 发布对话框前置步骤
- 出口: 完成后跳 T11 发布对话框,或返回 T06

## 3. 视觉参考
`docs/mockups/T10-redaction.html`

## 4. API

| 操作 | 端点 |
|---|---|
| 触发扫描 | `POST /api/v1/assets/{asset_id}/redaction/scan` → 异步,返回 job_id |
| 查询扫描结果 | `GET /api/v1/assets/{asset_id}/redaction/scan?job_id=` |
| 确认脱敏 | `POST /api/v1/assets/{asset_id}/redaction/confirm` body `{item_ids[]}` |
| 标记豁免 | `POST /api/v1/assets/{asset_id}/redaction/exempt` body `{item_id, reason}` |

## 5. 组件分解

```
src/features/redaction/
├── RedactionPage.tsx
├── components/
│   ├── ScanProgress.tsx            ← 扫描中的进度状态
│   ├── ItemList.tsx                ← 命中项列表,按类型分组
│   ├── ItemCard.tsx                ← 单项:类型 / 位置 / 上下文 / 操作
│   ├── ExemptDialog.tsx            ← 豁免理由输入
│   └── BulkActionBar.tsx           ← 全部脱敏 / 全部豁免 / 完成
└── hooks/
    ├── useRedactionScan.ts         ← polling job 状态
    └── useRedactionConfirm.ts
```

shadcn 用: `Card` `Checkbox` `Badge` `Button` `Dialog` `Progress` `Tabs`

## 6. 状态管理

- 扫描 job ID: useState + polling
- 选中项(批量操作):useState `Set<string>`

## 7. 必备状态

- [ ] Loading: 扫描中 Progress + "正在扫描 X 个章节"
- [ ] Empty: 无命中 → 绿色"无敏感内容,可直接发布" + "进入发布"按钮
- [ ] Error: 扫描失败 + 重新扫描
- [ ] Success: 列表 + 底部操作

## 8. 验收

- [ ] 类型分组: PII / 密钥/Token / 内部代号 / 自定义规则
- [ ] 每项显示: 高亮匹配文本 / 章节位置(跳转锚点)/ 命中规则
- [ ] 单项操作: 脱敏(替换为 [REDACTED] 或自定义)/ 豁免(必填理由)
- [ ] 批量: 选中后底部出"批量脱敏 X 项"
- [ ] 已处理项移到"已处理"tab,可撤销
- [ ] 全部处理完后,主操作变成"进入发布(→ T11)"
- [ ] 扫描是异步 job,polling 间隔 2s,超时 60s 报错

## 9. 已知陷阱

- 扫描 job 可能很慢,必须 polling 不能阻塞 UI
- 脱敏替换文本是配置化的(在 T13 项目设置里改),前端不能写死 `[REDACTED]`
- 豁免理由必填,会进审计日志(T14 看)
- 同一文档内同样的字符串只算一项,不要重复列出

## 10. Claude Code 指令
扫描 job 的 polling 用 TanStack Query `refetchInterval`,job 完成后改为 false。
